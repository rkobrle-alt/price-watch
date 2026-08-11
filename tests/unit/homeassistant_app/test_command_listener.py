"""Tests for the serialized Home Assistant maintenance command listener."""

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from threading import Event
from typing import TextIO, cast

import pytest

from applications.homeassistant.command_listener import (
    _MaintenanceCommandListener,
)
from applications.homeassistant.maintenance_command import (
    MaintenanceCommandProcessor,
)
from core.state import (
    ObservationRetentionPlan,
    ObservationRetentionResult,
    StateStoreError,
)
from infrastructure.persistence.migration import (
    MigrationArchiveError,
    MigrationExportResult,
)
from tests.unit.homeassistant_app.helpers import RecordingStream, TIMESTAMP


@dataclass(slots=True)
class _RetentionManager:
    removable: int
    failure: StateStoreError | None = None
    apply_calls: list[tuple[datetime, Path]] = field(default_factory=list)

    def plan(self, cutoff: datetime) -> ObservationRetentionPlan:
        if self.failure is not None:
            raise self.failure
        return ObservationRetentionPlan(
            cutoff,
            self.removable + 1,
            self.removable,
            1,
            0,
        )

    def apply(
        self,
        cutoff: datetime,
        backup_file: Path,
    ) -> ObservationRetentionResult:
        self.apply_calls.append((cutoff, backup_file))
        plan = self.plan(cutoff)
        self.removable = 0
        return ObservationRetentionResult(plan, backup_file)


@dataclass(slots=True)
class _RecordingLock(AbstractContextManager[object]):
    events: list[str] = field(default_factory=list)

    def __enter__(self) -> object:
        self.events.append("enter")
        return self

    def __exit__(self, *arguments: object) -> None:
        self.events.append("exit")


class _FailingInput:
    def readline(self) -> str:
        raise OSError("stdin failed")


def _processor(manager: _RetentionManager) -> MaintenanceCommandProcessor:
    return MaintenanceCommandProcessor(
        cast(object, manager),
        90,
        lambda timestamp: Path("backup.sqlite3"),
    )


def _listener(
    command_input: object,
    manager: _RetentionManager,
    stdout: RecordingStream,
    stderr: RecordingStream,
    lock: _RecordingLock,
    published: list[datetime],
) -> _MaintenanceCommandListener:
    return _MaintenanceCommandListener(
        cast(TextIO, command_input),
        cast(TextIO, stdout),
        cast(TextIO, stderr),
        lambda: TIMESTAMP,
        lock,
        _processor(manager),
        lambda timestamp: published.append(timestamp) is None,
    )


def test_listener_continues_after_invalid_and_stale_commands_until_eof() -> None:
    lines = StringIO(
        "\n"
        '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
        '"expected_removable_observation_count":2}\n'
        '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
        '"expected_removable_observation_count":1}\n'
        '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
        '"expected_removable_observation_count":0}\n'
    )
    manager = _RetentionManager(1)
    stdout = RecordingStream()
    stderr = RecordingStream()
    lock = _RecordingLock()
    published: list[datetime] = []

    _listener(lines, manager, stdout, stderr, lock, published).listen()

    assert "maintenance command error: maintenance command cannot be blank" in stderr.text
    assert "maintenance command stale: expected_removable=2 actual_removable=1" in stdout.text
    assert "status=applied removed=1" in stdout.text
    assert "status=no_changes retained=1" in stdout.text
    assert lock.events == ["enter", "exit"] * 3
    assert published == [TIMESTAMP, TIMESTAMP, TIMESTAMP]


def test_listener_reports_persistence_and_input_failures() -> None:
    command = (
        '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
        '"expected_removable_observation_count":1}\n'
    )
    manager = _RetentionManager(1, StateStoreError("database failed"))
    stdout = RecordingStream()
    stderr = RecordingStream()
    listener = _listener(
        StringIO(command), manager, stdout, stderr, _RecordingLock(), []
    )

    listener.listen()

    assert stdout.text == ""
    assert stderr.text == "maintenance command error: database failed\n"

    stderr = RecordingStream()
    _listener(
        _FailingInput(), manager, RecordingStream(), stderr, _RecordingLock(), []
    ).listen()
    assert stderr.text == "maintenance command input error: stdin failed\n"


def test_listener_start_returns_named_daemon_thread() -> None:
    listener = _listener(
        StringIO(""),
        _RetentionManager(0),
        RecordingStream(),
        RecordingStream(),
        _RecordingLock(),
        [],
    )

    thread = listener.start()
    thread.join(timeout=1)

    assert thread.name == "price-watch-maintenance"
    assert thread.daemon is True
    assert not thread.is_alive()


def test_listener_does_not_enter_shared_lock_until_it_is_available() -> None:
    entered = Event()
    released = Event()

    class _BlockingLock(AbstractContextManager[object]):
        def __enter__(self) -> object:
            entered.set()
            assert released.wait(timeout=1)
            return self

        def __exit__(self, *arguments: object) -> None:
            return None

    command = StringIO(
        '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
        '"expected_removable_observation_count":0}\n'
    )
    published: list[datetime] = []
    listener = _MaintenanceCommandListener(
        command,
        cast(TextIO, RecordingStream()),
        cast(TextIO, RecordingStream()),
        lambda: TIMESTAMP,
        _BlockingLock(),
        _processor(_RetentionManager(0)),
        lambda timestamp: published.append(timestamp) is None,
    )

    thread = listener.start()
    assert entered.wait(timeout=1)
    assert published == []
    released.set()
    thread.join(timeout=1)
    assert published == [TIMESTAMP]


def test_listener_exports_migration_and_continues_after_known_failure() -> None:
    command = (
        '{"command":"export_migration","confirmation":"wrong"}\n'
        '{"command":"export_migration","confirmation":"EXPORT_MIGRATION"}\n'
        '{"command":"export_migration","confirmation":"EXPORT_MIGRATION"}\n'
    )
    stdout = RecordingStream()
    stderr = RecordingStream()
    lock = _RecordingLock()
    calls = 0

    def export(timestamp: datetime) -> MigrationExportResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise MigrationArchiveError("disk failed")
        assert timestamp == TIMESTAMP
        return MigrationExportResult(Path("bundle.zip"), "a" * 64, "state.json")

    listener = _MaintenanceCommandListener(
        StringIO(command),
        cast(TextIO, stdout),
        cast(TextIO, stderr),
        lambda: TIMESTAMP,
        lock,
        None,
        None,
        export,
    )

    listener.listen()

    assert calls == 2
    assert lock.events == ["enter", "exit"] * 2
    assert "confirmation must be 'EXPORT_MIGRATION'" in stderr.text
    assert "migration command error: disk failed" in stderr.text
    assert stdout.text == (
        "migration export complete: file=bundle.zip "
        f"sha256={'a' * 64} state=state.json\n"
    )


def test_listener_reports_unavailable_command_handlers() -> None:
    retention = (
        '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
        '"expected_removable_observation_count":0}\n'
    )
    migration = (
        '{"command":"export_migration","confirmation":"EXPORT_MIGRATION"}\n'
    )
    stderr = RecordingStream()
    _MaintenanceCommandListener(
        StringIO(retention),
        cast(TextIO, RecordingStream()),
        cast(TextIO, stderr),
        lambda: TIMESTAMP,
        _RecordingLock(),
        None,
        None,
        lambda timestamp: MigrationExportResult(
            Path("bundle.zip"), "a" * 64, "state.json"
        ),
    ).listen()
    assert "retention command is not available" in stderr.text

    stderr = RecordingStream()
    _MaintenanceCommandListener(
        StringIO(migration),
        cast(TextIO, RecordingStream()),
        cast(TextIO, stderr),
        lambda: TIMESTAMP,
        _RecordingLock(),
        _processor(_RetentionManager(0)),
        lambda timestamp: True,
    ).listen()
    assert "migration export is not available" in stderr.text


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("command_input", object(), "command_input"),
        ("stdout", object(), "stdout"),
        ("stderr", object(), "stderr"),
        ("clock", object(), "clock"),
        ("operation_lock", object(), "operation_lock"),
        ("processor", object(), "processor"),
        ("publish_preview", object(), "publish_preview"),
        ("migration_exporter", object(), "migration_exporter"),
    ],
)
def test_listener_rejects_invalid_dependencies(
    field: str, value: object, message: str
) -> None:
    values: dict[str, object] = {
        "command_input": StringIO(""),
        "stdout": RecordingStream(),
        "stderr": RecordingStream(),
        "clock": lambda: TIMESTAMP,
        "operation_lock": _RecordingLock(),
        "processor": _processor(_RetentionManager(0)),
        "publish_preview": lambda timestamp: True,
        "migration_exporter": None,
    }
    values[field] = value

    with pytest.raises(TypeError, match=message):
        _MaintenanceCommandListener(**cast(dict, values))


@pytest.mark.parametrize(
    ("processor", "publisher"),
    [(_processor(_RetentionManager(0)), None), (None, lambda timestamp: True)],
)
def test_listener_requires_complete_retention_handler_pair(
    processor: object, publisher: object
) -> None:
    with pytest.raises(ValueError, match="configured together"):
        _MaintenanceCommandListener(
            StringIO(""),
            cast(TextIO, RecordingStream()),
            cast(TextIO, RecordingStream()),
            lambda: TIMESTAMP,
            _RecordingLock(),
            cast(MaintenanceCommandProcessor | None, processor),
            cast(object, publisher),
            lambda timestamp: MigrationExportResult(
                Path("bundle.zip"), "a" * 64, "state.json"
            ),
        )


def test_listener_requires_at_least_one_handler() -> None:
    with pytest.raises(ValueError, match="at least one"):
        _MaintenanceCommandListener(
            StringIO(""),
            cast(TextIO, RecordingStream()),
            cast(TextIO, RecordingStream()),
            lambda: TIMESTAMP,
            _RecordingLock(),
            None,
            None,
        )
