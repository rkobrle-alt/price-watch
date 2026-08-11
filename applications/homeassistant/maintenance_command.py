"""Parse and process explicit Home Assistant retention commands."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import cast

from core.state import (
    ObservationRetentionManager,
    ObservationRetentionPlan,
    ObservationRetentionResult,
)

_COMMAND = "apply_retention"
_CONFIRMATION = "APPLY_RETENTION"
_FIELDS = {
    "command",
    "confirmation",
    "expected_removable_observation_count",
}


class MaintenanceCommandStatus(str, Enum):
    """Describe the non-error outcome of one explicit maintenance command."""

    STALE_PLAN = "stale_plan"
    NO_CHANGES = "no_changes"
    APPLIED = "applied"


class MaintenanceCommandError(RuntimeError):
    """Report invalid external Home Assistant maintenance command data."""


@dataclass(frozen=True, slots=True)
class HomeAssistantMaintenanceCommand:
    """Request apply only for one operator-reviewed removable count."""

    expected_removable_observation_count: int

    def __post_init__(self) -> None:
        """Validate the immutable command."""
        _validate_count(
            self.expected_removable_observation_count,
            "expected_removable_observation_count",
        )


@dataclass(frozen=True, slots=True)
class MaintenanceCommandResult:
    """Describe one accepted command without hiding its reviewed plan."""

    status: MaintenanceCommandStatus
    timestamp: datetime
    retention_days: int
    plan: ObservationRetentionPlan
    removed_observation_count: int = 0
    backup_file: Path | None = None

    def __post_init__(self) -> None:
        """Validate the complete immutable command result."""
        if not isinstance(self.status, MaintenanceCommandStatus):
            raise TypeError("status must be a MaintenanceCommandStatus")
        _validate_timestamp(self.timestamp)
        _validate_positive_integer(self.retention_days, "retention_days")
        if not isinstance(self.plan, ObservationRetentionPlan):
            raise TypeError("plan must be an ObservationRetentionPlan")
        _validate_count(
            self.removed_observation_count,
            "removed_observation_count",
        )
        if self.backup_file is not None and not isinstance(
            self.backup_file,
            Path,
        ):
            raise TypeError("backup_file must be a Path or None")
        self._validate_outcome()

    def _validate_outcome(self) -> None:
        if self.status is MaintenanceCommandStatus.APPLIED:
            if self.backup_file is None:
                raise ValueError("applied result requires backup_file")
            if self.removed_observation_count <= 0:
                raise ValueError("applied result requires removed observations")
            if (
                self.removed_observation_count
                != self.plan.removable_observation_count
            ):
                raise ValueError("removed count must equal the applied plan")
            return
        if self.backup_file is not None:
            raise ValueError("non-applied result cannot contain backup_file")
        if self.removed_observation_count != 0:
            raise ValueError("non-applied result cannot remove observations")
        if (
            self.status is MaintenanceCommandStatus.NO_CHANGES
            and self.plan.removable_observation_count != 0
        ):
            raise ValueError("no-change result requires an empty plan")


class MaintenanceCommandProcessor:
    """Revalidate and explicitly apply one configured retention preview."""

    def __init__(
        self,
        retention_manager: ObservationRetentionManager,
        retention_days: int,
        backup_file_factory: Callable[[datetime], Path],
    ) -> None:
        """Configure injected retention and backup collaborators."""
        if not callable(getattr(retention_manager, "plan", None)) or not callable(
            getattr(retention_manager, "apply", None)
        ):
            raise TypeError("retention_manager must implement retention operations")
        _validate_positive_integer(retention_days, "retention_days")
        if not callable(backup_file_factory):
            raise TypeError("backup_file_factory must be callable")
        self._retention_manager = retention_manager
        self._retention_days = retention_days
        self._backup_file_factory = backup_file_factory

    def process(
        self,
        command: HomeAssistantMaintenanceCommand,
        timestamp: datetime,
    ) -> MaintenanceCommandResult:
        """Apply only a current plan matching the operator-reviewed count."""
        if not isinstance(command, HomeAssistantMaintenanceCommand):
            raise TypeError("command must be a HomeAssistantMaintenanceCommand")
        _validate_timestamp(timestamp)
        cutoff = timestamp - timedelta(days=self._retention_days)
        plan = self._retention_manager.plan(cutoff)
        if not isinstance(plan, ObservationRetentionPlan):
            raise TypeError("retention plan must be an ObservationRetentionPlan")
        if (
            plan.removable_observation_count
            != command.expected_removable_observation_count
        ):
            return MaintenanceCommandResult(
                MaintenanceCommandStatus.STALE_PLAN,
                timestamp,
                self._retention_days,
                plan,
            )
        if plan.removable_observation_count == 0:
            return MaintenanceCommandResult(
                MaintenanceCommandStatus.NO_CHANGES,
                timestamp,
                self._retention_days,
                plan,
            )
        backup_file = self._backup_file_factory(timestamp)
        if not isinstance(backup_file, Path):
            raise TypeError("backup_file_factory must return a Path")
        applied = self._retention_manager.apply(cutoff, backup_file)
        if not isinstance(applied, ObservationRetentionResult):
            raise TypeError("retention apply must return an ObservationRetentionResult")
        return MaintenanceCommandResult(
            MaintenanceCommandStatus.APPLIED,
            timestamp,
            self._retention_days,
            applied.plan,
            applied.plan.removable_observation_count,
            applied.backup_file,
        )


def parse_maintenance_command(line: str) -> HomeAssistantMaintenanceCommand:
    """Parse one strict JSON-lines Home Assistant maintenance command."""
    if not isinstance(line, str):
        raise TypeError("line must be a string")
    if not line.strip():
        raise MaintenanceCommandError("maintenance command cannot be blank")
    try:
        document = json.loads(line, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, MaintenanceCommandError) as error:
        if isinstance(error, MaintenanceCommandError):
            raise
        raise MaintenanceCommandError("maintenance command must be valid JSON") from error
    if not isinstance(document, dict):
        raise MaintenanceCommandError("maintenance command must be a JSON object")
    keys = set(document)
    if keys != _FIELDS:
        missing = sorted(_FIELDS - keys)
        unknown = sorted(keys - _FIELDS)
        detail = []
        if missing:
            detail.append(f"missing fields: {', '.join(missing)}")
        if unknown:
            detail.append(f"unknown fields: {', '.join(unknown)}")
        raise MaintenanceCommandError("; ".join(detail))
    if document["command"] != _COMMAND:
        raise MaintenanceCommandError(f"command must be {_COMMAND!r}")
    if document["confirmation"] != _CONFIRMATION:
        raise MaintenanceCommandError(
            f"confirmation must be {_CONFIRMATION!r}"
        )
    count = document["expected_removable_observation_count"]
    try:
        _validate_count(count, "expected_removable_observation_count")
    except (TypeError, ValueError) as error:
        raise MaintenanceCommandError(str(error)) from error
    return HomeAssistantMaintenanceCommand(cast(int, count))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MaintenanceCommandError(f"duplicate field: {key}")
        result[key] = value
    return result


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")


def _validate_count(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _validate_positive_integer(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
