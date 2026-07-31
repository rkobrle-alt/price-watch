"""Immutable command values produced by the CLI parser."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class SyncArguments:
    """Validated configuration for one synchronization command."""

    product_urls: tuple[str, ...]
    state_file: Path
    timeout_seconds: int = 10
    price_drop_percentage: Decimal | None = None
    price_drop_amount: Decimal | None = None

    def __post_init__(self) -> None:
        """Validate command argument types and numeric ranges."""
        if not isinstance(self.product_urls, tuple) or not all(
            isinstance(url, str) for url in self.product_urls
        ):
            raise TypeError("product_urls must be a tuple of strings")
        if not self.product_urls:
            raise ValueError("product_urls cannot be empty")
        if not isinstance(self.state_file, Path):
            raise TypeError("state_file must be a Path")
        if isinstance(self.timeout_seconds, bool) or not isinstance(
            self.timeout_seconds,
            int,
        ):
            raise TypeError("timeout_seconds must be an int")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        _validate_optional_decimal(
            self.price_drop_percentage,
            "price_drop_percentage",
            maximum=Decimal("100"),
        )
        _validate_optional_decimal(
            self.price_drop_amount,
            "price_drop_amount",
            maximum=None,
        )


@dataclass(frozen=True, slots=True)
class VersionArguments:
    """Represent the argument-free version command."""


CliArguments: TypeAlias = SyncArguments | VersionArguments


def _validate_optional_decimal(
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
