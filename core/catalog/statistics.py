"""Immutable catalog statistics and read-only contract."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from core.domain import ProviderId


@dataclass(frozen=True, slots=True)
class CatalogStatistics:
    """Summarize durable catalog membership and activity for one provider."""

    reference_count: int
    last_discovered_at: datetime | None
    last_refresh_attempt_at: datetime | None

    def __post_init__(self) -> None:
        """Validate counts and optional timezone-aware timestamps."""
        _validate_count(self.reference_count, "reference_count")
        _validate_optional_timestamp(
            self.last_discovered_at,
            "last_discovered_at",
        )
        _validate_optional_timestamp(
            self.last_refresh_attempt_at,
            "last_refresh_attempt_at",
        )


class CatalogStatisticsReader(Protocol):
    """Read provider-neutral durable catalog statistics."""

    def catalog_statistics(self, provider_id: ProviderId) -> CatalogStatistics:
        """Return the current aggregate statistics for one provider."""
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
