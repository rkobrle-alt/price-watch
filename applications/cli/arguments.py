"""Immutable command values produced by the CLI parser."""

from dataclasses import dataclass
from datetime import timedelta
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


@dataclass(frozen=True, slots=True)
class MaintenanceArguments:
    """Configure one read-only or explicitly applied retention operation."""

    database_file: Path
    retention_days: int
    apply: bool = False
    backup_file: Path | None = None

    def __post_init__(self) -> None:
        """Validate paths, retention duration and explicit apply pairing."""
        if not isinstance(self.database_file, Path):
            raise TypeError("database_file must be a Path")
        if isinstance(self.retention_days, bool) or not isinstance(
            self.retention_days,
            int,
        ):
            raise TypeError("retention_days must be an int")
        if self.retention_days <= 0:
            raise ValueError("retention_days must be positive")
        if not isinstance(self.apply, bool):
            raise TypeError("apply must be a bool")
        if self.backup_file is not None and not isinstance(
            self.backup_file,
            Path,
        ):
            raise TypeError("backup_file must be a Path or None")
        if self.apply != (self.backup_file is not None):
            raise ValueError("apply and backup_file must be supplied together")


@dataclass(frozen=True, slots=True)
class WatchArguments:
    """Validated configuration for repeated synchronization."""

    sync: SyncArguments
    interval: timedelta
    max_cycles: int | None = None

    def __post_init__(self) -> None:
        """Validate scheduling arguments."""
        if not isinstance(self.sync, SyncArguments):
            raise TypeError("sync must be SyncArguments")
        if not isinstance(self.interval, timedelta):
            raise TypeError("interval must be a timedelta")
        if self.interval <= timedelta(0):
            raise ValueError("interval must be positive")
        if self.max_cycles is not None:
            if isinstance(self.max_cycles, bool) or not isinstance(
                self.max_cycles,
                int,
            ):
                raise TypeError("max_cycles must be an int or None")
            if self.max_cycles <= 0:
                raise ValueError("max_cycles must be positive")


@dataclass(frozen=True, slots=True)
class SyncConfigurationArguments:
    """Select one synchronization configured by an explicit file."""

    config_file: Path

    def __post_init__(self) -> None:
        """Validate the explicit configuration path."""
        if not isinstance(self.config_file, Path):
            raise TypeError("config_file must be a Path")


@dataclass(frozen=True, slots=True)
class WatchConfigurationArguments:
    """Select repeated configured synchronization with an optional bound."""

    config_file: Path
    max_cycles: int | None = None

    def __post_init__(self) -> None:
        """Validate the path and optional process-lifetime bound."""
        if not isinstance(self.config_file, Path):
            raise TypeError("config_file must be a Path")
        if self.max_cycles is not None:
            if isinstance(self.max_cycles, bool) or not isinstance(
                self.max_cycles,
                int,
            ):
                raise TypeError("max_cycles must be an int or None")
            if self.max_cycles <= 0:
                raise ValueError("max_cycles must be positive")


CliArguments: TypeAlias = (
    MaintenanceArguments
    | SyncArguments
    | VersionArguments
    | WatchArguments
    | SyncConfigurationArguments
    | WatchConfigurationArguments
)


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
