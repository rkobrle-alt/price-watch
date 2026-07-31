"""Immutable validated application configuration."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    """Configure synchronization and optional interval scheduling."""

    product_urls: tuple[str, ...]
    state_file: Path
    timeout_seconds: int = 10
    price_drop_percentage: Decimal | None = None
    price_drop_amount: Decimal | None = None
    interval: timedelta | None = None

    def __post_init__(self) -> None:
        """Validate configuration types and invariants."""
        if not isinstance(self.product_urls, tuple) or not all(
            isinstance(url, str) for url in self.product_urls
        ):
            raise TypeError("product_urls must be a tuple of strings")
        if not self.product_urls:
            raise ValueError("product_urls cannot be empty")
        if any(not url.strip() for url in self.product_urls):
            raise ValueError("product_urls cannot contain blank values")
        if not isinstance(self.state_file, Path):
            raise TypeError("state_file must be a Path")
        if isinstance(self.timeout_seconds, bool) or not isinstance(
            self.timeout_seconds,
            int,
        ):
            raise TypeError("timeout_seconds must be an int")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        _validate_decimal(
            self.price_drop_percentage,
            "price_drop_percentage",
            maximum=Decimal("100"),
        )
        _validate_decimal(
            self.price_drop_amount,
            "price_drop_amount",
            maximum=None,
        )
        if self.interval is not None:
            if not isinstance(self.interval, timedelta):
                raise TypeError("interval must be a timedelta or None")
            if self.interval <= timedelta(0):
                raise ValueError("interval must be positive")


def _validate_decimal(
    value: object,
    field_name: str,
    *,
    maximum: Decimal | None,
) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal or None")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < Decimal("0") or (maximum is not None and value > maximum):
        raise ValueError(f"{field_name} is outside its allowed range")
