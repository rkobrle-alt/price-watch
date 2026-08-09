"""Immutable observation statistics and read-only contract."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ObservationStatistics:
    """Describe retained observations without changing their lifecycle."""

    observation_count: int
    observed_product_count: int
    first_observation_at: datetime | None
    last_observation_at: datetime | None
    storage_size_bytes: int

    def __post_init__(self) -> None:
        """Validate complete statistics and boundary timestamp presence."""
        _validate_count(self.observation_count, "observation_count")
        _validate_count(self.observed_product_count, "observed_product_count")
        _validate_count(self.storage_size_bytes, "storage_size_bytes")
        if self.observed_product_count > self.observation_count:
            raise ValueError(
                "observed_product_count cannot exceed observation_count"
            )
        _validate_optional_timestamp(
            self.first_observation_at,
            "first_observation_at",
        )
        _validate_optional_timestamp(
            self.last_observation_at,
            "last_observation_at",
        )
        timestamps_present = (
            self.first_observation_at is not None,
            self.last_observation_at is not None,
        )
        if self.observation_count == 0:
            if any(timestamps_present):
                raise ValueError("empty observations cannot have timestamps")
        elif not all(timestamps_present):
            raise ValueError("non-empty observations require both timestamps")


class ObservationStatisticsReader(Protocol):
    """Read non-destructive statistics for a durable observation store."""

    def observation_statistics(self) -> ObservationStatistics:
        """Return current statistics or raise the state persistence error."""
        ...


def _validate_count(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _validate_optional_timestamp(value: object, name: str) -> None:
    if value is None:
        return
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
