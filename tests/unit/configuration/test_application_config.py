"""Tests for immutable application configuration."""

from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from applications.configuration import ApplicationConfig


def _values() -> dict[str, object]:
    return {
        "product_urls": ("https://www.lidl.cz/tool/p100",),
        "state_file": Path("state.json"),
        "timeout_seconds": 10,
        "price_drop_percentage": Decimal("10.00"),
        "price_drop_amount": Decimal("25.00"),
        "interval": timedelta(seconds=60),
    }


def test_application_config_retains_exact_values_and_is_immutable() -> None:
    config = ApplicationConfig(**_values())

    assert config.price_drop_percentage == Decimal("10.00")
    assert config.price_drop_amount.as_tuple().exponent == -2
    with pytest.raises(FrozenInstanceError):
        config.timeout_seconds = 20


def test_application_config_supports_optional_defaults() -> None:
    config = ApplicationConfig(
        product_urls=("https://www.lidl.cz/tool/p100",),
        state_file=Path("state.json"),
    )

    assert config.timeout_seconds == 10
    assert config.price_drop_percentage is None
    assert config.price_drop_amount is None
    assert config.interval is None


@pytest.mark.parametrize(
    ("overrides", "exception_type"),
    [
        ({"product_urls": cast(tuple[str, ...], [])}, TypeError),
        ({"product_urls": (1,)}, TypeError),
        ({"product_urls": ()}, ValueError),
        ({"product_urls": (" ",)}, ValueError),
        ({"state_file": cast(Path, "state.json")}, TypeError),
        ({"timeout_seconds": True}, TypeError),
        ({"timeout_seconds": cast(int, "10")}, TypeError),
        ({"timeout_seconds": 0}, ValueError),
        ({"price_drop_percentage": cast(Decimal, 10)}, TypeError),
        ({"price_drop_percentage": Decimal("NaN")}, ValueError),
        ({"price_drop_percentage": Decimal("-1")}, ValueError),
        ({"price_drop_percentage": Decimal("101")}, ValueError),
        ({"price_drop_amount": cast(Decimal, 10)}, TypeError),
        ({"price_drop_amount": Decimal("Infinity")}, ValueError),
        ({"price_drop_amount": Decimal("-1")}, ValueError),
        ({"interval": cast(timedelta, 10)}, TypeError),
        ({"interval": timedelta(0)}, ValueError),
        ({"interval": timedelta(seconds=-1)}, ValueError),
    ],
)
def test_application_config_rejects_invalid_values(
    overrides: dict[str, object],
    exception_type: type[Exception],
) -> None:
    values = _values()
    values.update(overrides)

    with pytest.raises(exception_type):
        ApplicationConfig(**values)
