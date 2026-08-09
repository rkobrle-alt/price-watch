"""Immutable contracts for explicit observation-history retention."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ObservationRetentionPlan:
    """Describe one read-only retention decision for exact observations."""

    cutoff: datetime
    observation_count: int
    removable_observation_count: int
    retained_observation_count: int
    protected_observation_count: int

    def __post_init__(self) -> None:
        """Validate timestamp awareness and internally consistent counts."""
        _validate_cutoff(self.cutoff)
        _validate_count(self.observation_count, "observation_count")
        _validate_count(
            self.removable_observation_count,
            "removable_observation_count",
        )
        _validate_count(
            self.retained_observation_count,
            "retained_observation_count",
        )
        _validate_count(
            self.protected_observation_count,
            "protected_observation_count",
        )
        if (
            self.removable_observation_count
            + self.retained_observation_count
            != self.observation_count
        ):
            raise ValueError("retention counts must equal observation_count")
        if self.protected_observation_count > self.retained_observation_count:
            raise ValueError(
                "protected_observation_count cannot exceed retained count"
            )


@dataclass(frozen=True, slots=True)
class ObservationRetentionResult:
    """Describe one applied retention and its pre-deletion backup file."""

    plan: ObservationRetentionPlan
    backup_file: Path

    def __post_init__(self) -> None:
        """Validate the complete immutable result."""
        if not isinstance(self.plan, ObservationRetentionPlan):
            raise TypeError("plan must be an ObservationRetentionPlan")
        if not isinstance(self.backup_file, Path):
            raise TypeError("backup_file must be a Path")


class ObservationRetentionManager(Protocol):
    """Plan and explicitly apply backup-protected observation retention."""

    def plan(self, cutoff: datetime) -> ObservationRetentionPlan:
        """Return a retention plan without changing durable state."""
        ...

    def apply(
        self,
        cutoff: datetime,
        backup_file: Path,
    ) -> ObservationRetentionResult:
        """Back up current state and apply the recomputed retention plan."""
        ...


def validate_retention_cutoff(cutoff: object) -> datetime:
    """Validate a public retention cutoff for concrete implementations."""
    _validate_cutoff(cutoff)
    return cutoff


def _validate_cutoff(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("cutoff must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")


def _validate_count(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
