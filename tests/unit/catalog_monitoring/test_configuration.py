"""Tests for immutable catalog monitoring application configuration."""

from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from applications.catalog_monitoring import CatalogMonitoringConfig


def test_configuration_preserves_exact_values_and_is_immutable() -> None:
    config = CatalogMonitoringConfig(
        database_file=Path("catalog.sqlite3"),
        interval=timedelta(minutes=5),
        timeout_seconds=12,
        batch_size=30,
        discovery_interval_cycles=48,
        price_drop_percentage=Decimal("20.00"),
        price_drop_amount=Decimal("500.00"),
    )

    assert config.price_drop_percentage == Decimal("20.00")
    assert config.price_drop_amount == Decimal("500.00")
    assert not hasattr(config, "__dict__")
    with pytest.raises(FrozenInstanceError):
        config.batch_size = 5  # type: ignore[misc]


def test_configuration_uses_catalog_defaults() -> None:
    config = CatalogMonitoringConfig(
        Path("catalog.sqlite3"),
        timedelta(minutes=5),
    )

    assert config.timeout_seconds == 10
    assert config.batch_size == 25
    assert config.discovery_interval_cycles == 288
    assert config.price_drop_percentage == Decimal("20.00")
    assert config.price_drop_amount is None


@pytest.mark.parametrize(
    ("field", "value", "exception_type"),
    [
        ("database_file", "catalog.sqlite3", TypeError),
        ("interval", 300, TypeError),
        ("interval", timedelta(0), ValueError),
        ("timeout_seconds", True, TypeError),
        ("timeout_seconds", 0, ValueError),
        ("batch_size", "25", TypeError),
        ("batch_size", -1, ValueError),
        ("discovery_interval_cycles", 1.5, TypeError),
        ("discovery_interval_cycles", 0, ValueError),
        ("price_drop_percentage", "20", TypeError),
        ("price_drop_percentage", Decimal("NaN"), ValueError),
        ("price_drop_percentage", Decimal("101"), ValueError),
        ("price_drop_amount", 20, TypeError),
        ("price_drop_amount", Decimal("Infinity"), ValueError),
        ("price_drop_amount", Decimal("-1"), ValueError),
    ],
)
def test_configuration_rejects_invalid_members(
    field: str,
    value: object,
    exception_type: type[Exception],
) -> None:
    arguments: dict[str, object] = {
        "database_file": Path("catalog.sqlite3"),
        "interval": timedelta(minutes=5),
    }
    arguments[field] = value

    with pytest.raises(exception_type, match=field):
        CatalogMonitoringConfig(**arguments)  # type: ignore[arg-type]
