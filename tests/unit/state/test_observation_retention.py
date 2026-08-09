"""Tests for immutable observation-retention contracts."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from core.state import (
    ObservationRetentionManager,
    ObservationRetentionPlan,
    ObservationRetentionResult,
)

_CUTOFF = datetime(2026, 8, 1, tzinfo=UTC)


class _Manager:
    def plan(self, cutoff: datetime) -> ObservationRetentionPlan:
        return ObservationRetentionPlan(cutoff, 5, 2, 3, 2)

    def apply(
        self,
        cutoff: datetime,
        backup_file: Path,
    ) -> ObservationRetentionResult:
        return ObservationRetentionResult(self.plan(cutoff), backup_file)


def test_values_are_immutable_slotted_and_manager_is_structural() -> None:
    manager: ObservationRetentionManager = _Manager()
    plan = manager.plan(_CUTOFF)
    result = manager.apply(_CUTOFF, Path("backup.sqlite3"))

    assert result == ObservationRetentionResult(plan, Path("backup.sqlite3"))
    assert not hasattr(plan, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        plan.observation_count = 4  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "exception_type", "message"),
    [
        ({"cutoff": "now"}, TypeError, "cutoff"),
        ({"cutoff": datetime(2026, 8, 1)}, ValueError, "timezone-aware"),
        ({"observation_count": True}, TypeError, "observation_count"),
        ({"removable_observation_count": -1}, ValueError, "removable"),
        ({"retained_observation_count": "3"}, TypeError, "retained"),
        ({"protected_observation_count": -1}, ValueError, "protected"),
        ({"observation_count": 6}, ValueError, "must equal"),
        ({"protected_observation_count": 4}, ValueError, "cannot exceed"),
    ],
)
def test_plan_rejects_invalid_values(
    changes: dict[str, object],
    exception_type: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "cutoff": _CUTOFF,
        "observation_count": 5,
        "removable_observation_count": 2,
        "retained_observation_count": 3,
        "protected_observation_count": 2,
    }
    values.update(changes)

    with pytest.raises(exception_type, match=message):
        ObservationRetentionPlan(**cast(dict, values))


@pytest.mark.parametrize(
    ("plan", "backup_file", "exception_type", "message"),
    [
        (object(), Path("backup.sqlite3"), TypeError, "plan"),
        (
            ObservationRetentionPlan(_CUTOFF, 0, 0, 0, 0),
            "backup.sqlite3",
            TypeError,
            "backup_file",
        ),
    ],
)
def test_result_rejects_invalid_values(
    plan: object,
    backup_file: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        ObservationRetentionResult(
            cast(ObservationRetentionPlan, plan),
            cast(Path, backup_file),
        )
