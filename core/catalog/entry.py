"""Immutable durable catalog entry."""

from dataclasses import dataclass
from datetime import datetime

from core.catalog.reference import ProductReference


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """Track the first and most recent discovery of a product reference."""

    reference: ProductReference
    first_seen_at: datetime
    last_seen_at: datetime

    def __post_init__(self) -> None:
        """Validate reference and chronological timestamp invariants."""
        if not isinstance(self.reference, ProductReference):
            raise TypeError("reference must be a ProductReference")
        _validate_timestamp(self.first_seen_at, "first_seen_at")
        _validate_timestamp(self.last_seen_at, "last_seen_at")
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("last_seen_at cannot precede first_seen_at")


def _validate_timestamp(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
