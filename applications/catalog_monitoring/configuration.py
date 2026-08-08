"""Immutable application configuration for catalog monitoring."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CatalogMonitoringConfig:
    """Configure durable bounded catalog monitoring."""

    database_file: Path
    interval: timedelta
    timeout_seconds: int = 10
    batch_size: int = 25
    discovery_interval_cycles: int = 288
    price_drop_percentage: Decimal | None = Decimal("20.00")
    price_drop_amount: Decimal | None = None

    def __post_init__(self) -> None:
        """Validate paths, scheduling bounds and exact thresholds."""
        if not isinstance(self.database_file, Path):
            raise TypeError("database_file must be a Path")
        if not isinstance(self.interval, timedelta):
            raise TypeError("interval must be a timedelta")
        if self.interval <= timedelta(0):
            raise ValueError("interval must be positive")
        _validate_positive_integer(self.timeout_seconds, "timeout_seconds")
        _validate_positive_integer(self.batch_size, "batch_size")
        _validate_positive_integer(
            self.discovery_interval_cycles,
            "discovery_interval_cycles",
        )
        _validate_decimal(
            self.price_drop_percentage,
            "price_drop_percentage",
            Decimal("100"),
        )
        _validate_decimal(
            self.price_drop_amount,
            "price_drop_amount",
            None,
        )


def _validate_positive_integer(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _validate_decimal(
    value: object,
    name: str,
    maximum: Decimal | None,
) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal or None")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if value < Decimal("0") or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside its allowed range")
