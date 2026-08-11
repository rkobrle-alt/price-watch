"""Tests for strict Home Assistant retention-command processing."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from applications.homeassistant import (
    HomeAssistantMaintenanceCommand,
    MaintenanceCommandError,
    MaintenanceCommandProcessor,
    MaintenanceCommandResult,
    MaintenanceCommandStatus,
    parse_maintenance_command,
)
from core.state import ObservationRetentionPlan, ObservationRetentionResult
from tests.unit.homeassistant_app.helpers import TIMESTAMP


class _RetentionManager:
    def __init__(
        self,
        plan: ObservationRetentionPlan,
        applied: ObservationRetentionResult | object | None = None,
        failure: BaseException | None = None,
    ) -> None:
        self.plan_result = plan
        self.applied = applied
        self.failure = failure
        self.plan_calls: list[datetime] = []
        self.apply_calls: list[tuple[datetime, Path]] = []

    def plan(self, cutoff: datetime) -> ObservationRetentionPlan:
        self.plan_calls.append(cutoff)
        return self.plan_result

    def apply(
        self,
        cutoff: datetime,
        backup_file: Path,
    ) -> ObservationRetentionResult:
        self.apply_calls.append((cutoff, backup_file))
        if self.failure is not None:
            raise self.failure
        return cast(ObservationRetentionResult, self.applied)


def _plan(removable: int) -> ObservationRetentionPlan:
    return ObservationRetentionPlan(
        TIMESTAMP - timedelta(days=90),
        removable + 2,
        removable,
        2,
        1,
    )


def test_parser_accepts_only_the_exact_command_and_value_is_frozen() -> None:
    command = parse_maintenance_command(
        '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
        '"expected_removable_observation_count":12}'
    )

    assert command == HomeAssistantMaintenanceCommand(12)
    with pytest.raises(FrozenInstanceError):
        command.expected_removable_observation_count = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("", "blank"),
        ("not-json", "valid JSON"),
        ("[]", "JSON object"),
        ('{"command":"apply_retention"}', "missing fields"),
        (
            '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
            '"expected_removable_observation_count":0,"extra":1}',
            "unknown fields",
        ),
        (
            '{"command":"apply_retention","command":"apply_retention",'
            '"confirmation":"APPLY_RETENTION",'
            '"expected_removable_observation_count":0}',
            "duplicate field",
        ),
        (
            '{"command":"delete","confirmation":"APPLY_RETENTION",'
            '"expected_removable_observation_count":0}',
            "command must be",
        ),
        (
            '{"command":"apply_retention","confirmation":"yes",'
            '"expected_removable_observation_count":0}',
            "confirmation must be",
        ),
        (
            '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
            '"expected_removable_observation_count":true}',
            "must be an int",
        ),
        (
            '{"command":"apply_retention","confirmation":"APPLY_RETENTION",'
            '"expected_removable_observation_count":-1}',
            "cannot be negative",
        ),
    ],
)
def test_parser_rejects_invalid_external_data(line: str, message: str) -> None:
    with pytest.raises(MaintenanceCommandError, match=message):
        parse_maintenance_command(line)


def test_parser_rejects_non_string_argument() -> None:
    with pytest.raises(TypeError, match="line"):
        parse_maintenance_command(cast(str, object()))


def test_processor_rejects_stale_plan_without_backup_or_apply() -> None:
    manager = _RetentionManager(_plan(3))
    backup_calls: list[datetime] = []
    processor = MaintenanceCommandProcessor(
        cast(object, manager),
        90,
        lambda timestamp: backup_calls.append(timestamp) or Path("backup"),
    )

    result = processor.process(HomeAssistantMaintenanceCommand(2), TIMESTAMP)

    assert result.status is MaintenanceCommandStatus.STALE_PLAN
    assert result.plan == _plan(3)
    assert manager.plan_calls == [TIMESTAMP - timedelta(days=90)]
    assert manager.apply_calls == []
    assert backup_calls == []


def test_processor_returns_no_changes_without_backup_or_apply() -> None:
    manager = _RetentionManager(_plan(0))
    processor = MaintenanceCommandProcessor(
        cast(object, manager), 90, lambda timestamp: Path("unused")
    )

    result = processor.process(HomeAssistantMaintenanceCommand(0), TIMESTAMP)

    assert result.status is MaintenanceCommandStatus.NO_CHANGES
    assert result.removed_observation_count == 0
    assert result.backup_file is None
    assert manager.apply_calls == []


def test_processor_applies_matching_positive_plan_and_preserves_failure() -> None:
    plan = _plan(3)
    backup = Path("backup.sqlite3")
    applied = ObservationRetentionResult(plan, backup)
    manager = _RetentionManager(plan, applied)
    processor = MaintenanceCommandProcessor(
        cast(object, manager), 90, lambda timestamp: backup
    )

    result = processor.process(HomeAssistantMaintenanceCommand(3), TIMESTAMP)

    assert result == MaintenanceCommandResult(
        MaintenanceCommandStatus.APPLIED,
        TIMESTAMP,
        90,
        plan,
        3,
        backup,
    )
    assert manager.apply_calls == [(TIMESTAMP - timedelta(days=90), backup)]

    failure = RuntimeError("apply failed")
    manager.failure = failure
    with pytest.raises(RuntimeError) as captured:
        processor.process(HomeAssistantMaintenanceCommand(3), TIMESTAMP)
    assert captured.value is failure


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda timestamp: "backup", "return a Path"),
        (lambda timestamp: (_ for _ in ()).throw(RuntimeError("backup failed")), "backup failed"),
    ],
)
def test_processor_rejects_or_preserves_backup_factory_failure(
    factory: object,
    message: str,
) -> None:
    processor = MaintenanceCommandProcessor(
        cast(object, _RetentionManager(_plan(1))),
        90,
        cast(object, factory),
    )
    with pytest.raises((TypeError, RuntimeError), match=message):
        processor.process(HomeAssistantMaintenanceCommand(1), TIMESTAMP)


@pytest.mark.parametrize(
    ("arguments", "exception_type", "message"),
    [
        ((object(), 90, lambda timestamp: Path("x")), TypeError, "retention_manager"),
        ((cast(object, _RetentionManager(_plan(0))), True, lambda timestamp: Path("x")), TypeError, "retention_days"),
        ((cast(object, _RetentionManager(_plan(0))), 0, lambda timestamp: Path("x")), ValueError, "positive"),
        ((cast(object, _RetentionManager(_plan(0))), 90, object()), TypeError, "backup_file_factory"),
    ],
)
def test_processor_rejects_invalid_dependencies(
    arguments: tuple[object, ...],
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        MaintenanceCommandProcessor(*cast(tuple, arguments))


def test_processor_validates_public_arguments_and_collaborator_results() -> None:
    processor = MaintenanceCommandProcessor(
        cast(object, _RetentionManager(_plan(0))),
        90,
        lambda timestamp: Path("x"),
    )
    with pytest.raises(TypeError, match="command"):
        processor.process(cast(HomeAssistantMaintenanceCommand, object()), TIMESTAMP)
    with pytest.raises(TypeError, match="timestamp"):
        processor.process(HomeAssistantMaintenanceCommand(0), cast(datetime, "now"))
    with pytest.raises(ValueError, match="timezone-aware"):
        processor.process(HomeAssistantMaintenanceCommand(0), datetime(2026, 8, 1))

    manager = _RetentionManager(cast(ObservationRetentionPlan, object()))
    invalid = MaintenanceCommandProcessor(
        cast(object, manager), 90, lambda timestamp: Path("x")
    )
    with pytest.raises(TypeError, match="retention plan"):
        invalid.process(HomeAssistantMaintenanceCommand(0), TIMESTAMP)

    manager = _RetentionManager(_plan(1), object())
    invalid = MaintenanceCommandProcessor(
        cast(object, manager), 90, lambda timestamp: Path("x")
    )
    with pytest.raises(TypeError, match="retention apply"):
        invalid.process(HomeAssistantMaintenanceCommand(1), TIMESTAMP)


@pytest.mark.parametrize(
    ("arguments", "exception_type", "message"),
    [
        ((-1,), ValueError, "negative"),
        ((True,), TypeError, "int"),
    ],
)
def test_command_rejects_invalid_count(
    arguments: tuple[object, ...], exception_type: type[Exception], message: str
) -> None:
    with pytest.raises(exception_type, match=message):
        HomeAssistantMaintenanceCommand(*cast(tuple, arguments))


def test_result_rejects_inconsistent_values() -> None:
    plan = _plan(1)
    valid = (
        MaintenanceCommandStatus.STALE_PLAN,
        TIMESTAMP,
        90,
        plan,
    )
    cases = [
        (("applied", *valid[1:]), TypeError, "status"),
        ((valid[0], "now", *valid[2:]), TypeError, "timestamp"),
        ((valid[0], datetime(2026, 8, 1), *valid[2:]), ValueError, "timezone-aware"),
        ((valid[0], TIMESTAMP, True, plan), TypeError, "retention_days"),
        ((valid[0], TIMESTAMP, 0, plan), ValueError, "positive"),
        ((valid[0], TIMESTAMP, 90, object()), TypeError, "plan"),
        ((*valid, True), TypeError, "removed_observation_count"),
        ((*valid, 0, "backup"), TypeError, "backup_file"),
        ((MaintenanceCommandStatus.APPLIED, TIMESTAMP, 90, plan, 1, None), ValueError, "backup_file"),
        ((MaintenanceCommandStatus.APPLIED, TIMESTAMP, 90, plan, 0, Path("x")), ValueError, "removed"),
        ((MaintenanceCommandStatus.APPLIED, TIMESTAMP, 90, plan, 2, Path("x")), ValueError, "equal"),
        ((*valid, 0, Path("x")), ValueError, "non-applied"),
        ((*valid, 1, None), ValueError, "non-applied"),
        ((MaintenanceCommandStatus.NO_CHANGES, TIMESTAMP, 90, plan), ValueError, "empty plan"),
    ]
    for arguments, exception_type, message in cases:
        with pytest.raises(exception_type, match=message):
            MaintenanceCommandResult(*cast(tuple, arguments))
