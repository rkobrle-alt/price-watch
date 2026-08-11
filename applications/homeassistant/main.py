"""Home Assistant App process boundary and outcome mapping."""

import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TextIO
from uuid import UUID, uuid4

from applications.homeassistant.composition import (
    _HomeAssistantComposition,
    _compose_homeassistant,
)
from applications.homeassistant.command_listener import (
    _MaintenanceCommandListener,
)
from applications.homeassistant.configuration import parse_homeassistant_options
from applications.homeassistant.cycle import (
    execute_catalog_cycle as _execute_catalog_cycle,
    execute_explicit_cycle as _execute_cycle,
    publish_maintenance_status as _publish_maintenance_status,
    publish_storage_warning as _publish_storage_warning,
)
from applications.homeassistant.maintenance_command import (
    MaintenanceCommandProcessor,
)
from applications.scheduler import IntervalScheduler
from core.catalog import CatalogStoreError
from core.configuration import ConfigurationError
from core.notifications import (
    DailyDigestReservationError,
    NotificationError,
    NotificationReservationError,
)
from core.rules import RuleError
from core.scheduler import Delay, SchedulerError
from core.state import StateStoreError
from infrastructure.configuration.json import JsonConfigurationLoader
from infrastructure.scheduler import SystemDelay
from infrastructure.persistence.sqlite import (
    TimestampedRetentionBackupFileFactory,
)

_DATA_DIRECTORY = Path("/data")
_OPTIONS_PATH = _DATA_DIRECTORY / "options.json"


def run(
    options: Mapping[str, object],
    access_token: str,
    stdout: TextIO,
    stderr: TextIO,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
    delay: Delay,
    *,
    data_directory: Path = _DATA_DIRECTORY,
    max_cycles: int | None = None,
    command_input: TextIO | None = None,
) -> int:
    """Run the Supervisor-hosted monitor with explicit process dependencies."""
    _validate_dependencies(
        options,
        access_token,
        stdout,
        stderr,
        clock,
        notification_id_factory,
        delay,
        data_directory,
        max_cycles,
        command_input,
    )
    if not access_token.strip():
        _write(stderr, "error: SUPERVISOR_TOKEN cannot be blank\n")
        return 2
    try:
        config = parse_homeassistant_options(options, data_directory)
        composition = _compose_homeassistant(
            config,
            access_token,
            clock,
            notification_id_factory,
        )
    except (ConfigurationError, ValueError) as error:
        _write(stderr, f"error: {error}\n")
        return 2

    operation_lock = Lock()
    maintenance_context = composition.maintenance_status
    if command_input is not None and maintenance_context is not None:
        maintenance_context = replace(
            maintenance_context,
            apply_available=True,
        )
        composition = replace(
            composition,
            maintenance_status=maintenance_context,
        )

    completed = 0
    provider_error_cycles = 0
    catalog_error_cycles = 0
    status_error_cycles = 0

    def cycle() -> None:
        nonlocal completed, provider_error_cycles
        nonlocal catalog_error_cycles, status_error_cycles
        with operation_lock:
            timestamp = clock()
            if composition.catalog_workflow is None:
                result, status_published = _execute_cycle(
                    composition,
                    stdout,
                    stderr,
                    timestamp,
                )
                has_provider_errors = bool(result.provider_errors)
                has_catalog_error = False
            else:
                try:
                    catalog_result, status_published = _execute_catalog_cycle(
                        composition,
                        stdout,
                        stderr,
                        timestamp,
                        completed % composition.discovery_interval_cycles == 0,
                    )
                except (
                    CatalogStoreError,
                    DailyDigestReservationError,
                    NotificationReservationError,
                    StateStoreError,
                ):
                    _publish_storage_warning(composition, timestamp, stderr)
                    raise
                synchronization = catalog_result.synchronization
                has_provider_errors = bool(
                    synchronization is not None
                    and synchronization.provider_errors
                )
                has_catalog_error = catalog_result.catalog_error is not None
            completed += 1
            if has_provider_errors:
                provider_error_cycles += 1
            if has_catalog_error:
                catalog_error_cycles += 1
            if not status_published:
                status_error_cycles += 1

    if command_input is not None and maintenance_context is not None:
        processor = MaintenanceCommandProcessor(
            maintenance_context.retention_manager,
            maintenance_context.retention_days,
            TimestampedRetentionBackupFileFactory(
                data_directory / "retention-backups"
            ),
        )
        _MaintenanceCommandListener(
            command_input,
            stdout,
            stderr,
            clock,
            operation_lock,
            processor,
            lambda timestamp: _publish_maintenance_status(
                composition,
                timestamp,
                stderr,
            ),
        ).start()

    scheduler = IntervalScheduler(cycle, delay)
    try:
        result = scheduler.run(composition.interval, max_cycles)
    except KeyboardInterrupt:
        _write_watch_outcome(
            stdout,
            "watch stopped",
            completed,
            provider_error_cycles,
            catalog_error_cycles,
            status_error_cycles,
            composition.catalog_workflow is not None,
        )
        return 130
    except (
        CatalogStoreError,
        DailyDigestReservationError,
        StateStoreError,
        RuleError,
        NotificationError,
        NotificationReservationError,
        SchedulerError,
    ) as error:
        _write(stderr, f"error: {error}\n")
        return 1

    _write_watch_outcome(
        stdout,
        "watch complete",
        result.cycles_completed,
        provider_error_cycles,
        catalog_error_cycles,
        status_error_cycles,
        composition.catalog_workflow is not None,
    )
    return 1 if (
        provider_error_cycles or catalog_error_cycles or status_error_cycles
    ) else 0


def main() -> int:
    """Run from Supervisor-managed options, token and process facilities."""
    access_token = os.environ.get("SUPERVISOR_TOKEN")
    if access_token is None or not access_token.strip():
        _write(sys.stderr, "error: SUPERVISOR_TOKEN is required\n")
        return 2
    try:
        options = JsonConfigurationLoader().load(_OPTIONS_PATH)
    except ConfigurationError as error:
        _write(sys.stderr, f"error: {error}\n")
        return 2
    return run(
        options,
        access_token,
        sys.stdout,
        sys.stderr,
        lambda: datetime.now(UTC),
        uuid4,
        SystemDelay(),
        data_directory=_DATA_DIRECTORY,
        command_input=sys.stdin,
    )


def _write_watch_outcome(
    stream: TextIO,
    label: str,
    cycles: int,
    provider_error_cycles: int,
    catalog_error_cycles: int,
    status_error_cycles: int,
    catalog_mode: bool,
) -> None:
    catalog_text = (
        f"catalog_error_cycles={catalog_error_cycles} " if catalog_mode else ""
    )
    _write(
        stream,
        f"{label}: cycles={cycles} "
        f"provider_error_cycles={provider_error_cycles} "
        f"{catalog_text}"
        f"status_error_cycles={status_error_cycles}\n",
    )


def _validate_dependencies(
    options: object,
    access_token: object,
    stdout: object,
    stderr: object,
    clock: object,
    notification_id_factory: object,
    delay: object,
    data_directory: object,
    max_cycles: object,
    command_input: object,
) -> None:
    if not isinstance(options, Mapping):
        raise TypeError("options must be a Mapping")
    if not isinstance(access_token, str):
        raise TypeError("access_token must be a string")
    _validate_stream(stdout, "stdout")
    _validate_stream(stderr, "stderr")
    if not callable(clock):
        raise TypeError("clock must be callable")
    if not callable(notification_id_factory):
        raise TypeError("notification_id_factory must be callable")
    if not callable(getattr(delay, "wait", None)):
        raise TypeError("delay must expose a callable wait method")
    if not isinstance(data_directory, Path):
        raise TypeError("data_directory must be a Path")
    if max_cycles is not None:
        if isinstance(max_cycles, bool) or not isinstance(max_cycles, int):
            raise TypeError("max_cycles must be an int or None")
        if max_cycles <= 0:
            raise ValueError("max_cycles must be positive")
    if command_input is not None and not callable(
        getattr(command_input, "readline", None)
    ):
        raise TypeError(
            "command_input must expose a callable readline method or be None"
        )


def _validate_stream(stream: object, name: str) -> None:
    if not callable(getattr(stream, "write", None)) or not callable(
        getattr(stream, "flush", None)
    ):
        raise TypeError(f"{name} must expose callable write and flush methods")


def _write(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()
