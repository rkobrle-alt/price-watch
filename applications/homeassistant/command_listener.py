"""Listen for explicit Home Assistant App commands on an injected stream."""

import json

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from threading import Thread
from typing import TextIO

from applications.homeassistant.maintenance_command import (
    HomeAssistantMaintenanceCommand,
    MaintenanceCommandError,
    MaintenanceCommandProcessor,
    MaintenanceCommandResult,
    MaintenanceCommandStatus,
    parse_maintenance_command,
)
from applications.homeassistant.migration import (
    MigrationCommandError,
    parse_migration_export_command,
)
from core.state import StateStoreError
from infrastructure.persistence.migration import (
    MigrationArchiveError,
    MigrationExportResult,
)


class _MaintenanceCommandListener:
    """Read, serialize and report explicit retention and migration commands."""

    def __init__(
        self,
        command_input: TextIO,
        stdout: TextIO,
        stderr: TextIO,
        clock: Callable[[], datetime],
        operation_lock: AbstractContextManager[object],
        processor: MaintenanceCommandProcessor | None,
        publish_preview: Callable[[datetime], bool] | None,
        migration_exporter: Callable[[datetime], MigrationExportResult] | None = None,
    ) -> None:
        if not callable(getattr(command_input, "readline", None)):
            raise TypeError("command_input must expose a callable readline method")
        _validate_stream(stdout, "stdout")
        _validate_stream(stderr, "stderr")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(getattr(operation_lock, "__enter__", None)) or not callable(
            getattr(operation_lock, "__exit__", None)
        ):
            raise TypeError("operation_lock must be a context manager")
        if processor is not None and not isinstance(
            processor, MaintenanceCommandProcessor
        ):
            raise TypeError("processor must be a MaintenanceCommandProcessor or None")
        if publish_preview is not None and not callable(publish_preview):
            raise TypeError("publish_preview must be callable or None")
        if (processor is None) != (publish_preview is None):
            raise ValueError("processor and publish_preview must be configured together")
        if migration_exporter is not None and not callable(migration_exporter):
            raise TypeError("migration_exporter must be callable or None")
        if processor is None and migration_exporter is None:
            raise ValueError("at least one command handler must be configured")
        self._command_input = command_input
        self._stdout = stdout
        self._stderr = stderr
        self._clock = clock
        self._operation_lock = operation_lock
        self._processor = processor
        self._publish_preview = publish_preview
        self._migration_exporter = migration_exporter

    def start(self) -> Thread:
        """Start one daemon listener and return its thread handle."""
        thread = Thread(
            target=self.listen,
            name="price-watch-maintenance",
            daemon=True,
        )
        thread.start()
        return thread

    def listen(self) -> None:
        """Process complete command lines until the injected stream reaches EOF."""
        while True:
            try:
                line = self._command_input.readline()
            except OSError as error:
                _write(self._stderr, f"maintenance command input error: {error}\n")
                return
            if line == "":
                return
            if _requests_migration_export(line):
                self._process_migration_export(line)
                continue
            try:
                command = parse_maintenance_command(line)
            except MaintenanceCommandError as error:
                _write(self._stderr, f"maintenance command error: {error}\n")
                continue
            try:
                with self._operation_lock:
                    timestamp = self._clock()
                    if self._processor is None or self._publish_preview is None:
                        raise MaintenanceCommandError(
                            "retention command is not available"
                        )
                    result = self._processor.process(command, timestamp)
                    self._publish_preview(timestamp)
            except (MaintenanceCommandError, StateStoreError) as error:
                _write(self._stderr, f"maintenance command error: {error}\n")
                continue
            _write(self._stdout, _format_result(command, result))

    def _process_migration_export(self, line: str) -> None:
        try:
            parse_migration_export_command(line)
            if self._migration_exporter is None:
                raise MigrationCommandError("migration export is not available")
            with self._operation_lock:
                result = self._migration_exporter(self._clock())
        except (MigrationCommandError, MigrationArchiveError) as error:
            _write(self._stderr, f"migration command error: {error}\n")
            return
        _write(
            self._stdout,
            "migration export complete: "
            f"file={result.archive_file} "
            f"sha256={result.archive_sha256} "
            f"state={result.state_file_name}\n",
        )


def _format_result(
    command: HomeAssistantMaintenanceCommand,
    result: MaintenanceCommandResult,
) -> str:
    if result.status is MaintenanceCommandStatus.STALE_PLAN:
        return (
            "maintenance command stale: "
            "expected_removable="
            f"{command.expected_removable_observation_count} "
            "actual_removable="
            f"{result.plan.removable_observation_count}\n"
        )
    if result.status is MaintenanceCommandStatus.NO_CHANGES:
        return (
            "maintenance command complete: status=no_changes "
            f"retained={result.plan.retained_observation_count}\n"
        )
    return (
        "maintenance command complete: status=applied "
        f"removed={result.removed_observation_count} "
        f"retained={result.plan.retained_observation_count} "
        f"protected={result.plan.protected_observation_count} "
        f"backup={result.backup_file}\n"
    )


def _validate_stream(stream: object, name: str) -> None:
    if not callable(getattr(stream, "write", None)) or not callable(
        getattr(stream, "flush", None)
    ):
        raise TypeError(f"{name} must expose callable write and flush methods")


def _write(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()


def _requests_migration_export(line: str) -> bool:
    try:
        document = json.loads(line)
    except (ValueError, TypeError):
        return False
    return isinstance(document, dict) and document.get("command") == "export_migration"
