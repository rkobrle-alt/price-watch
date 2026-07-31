"""Tests for immutable CLI command values."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from applications.cli.arguments import SyncArguments, VersionArguments


def test_sync_arguments_retain_exact_values_and_are_immutable() -> None:
    arguments = SyncArguments(
        product_urls=("https://www.lidl.cz/tool/p100",),
        state_file=Path("state.json"),
        timeout_seconds=15,
        price_drop_percentage=Decimal("10.50"),
        price_drop_amount=Decimal("250.00"),
    )

    assert arguments.price_drop_percentage == Decimal("10.50")
    assert arguments.price_drop_amount.as_tuple().exponent == -2
    with pytest.raises(FrozenInstanceError):
        arguments.timeout_seconds = 20


def test_version_arguments_is_immutable() -> None:
    arguments = VersionArguments()

    with pytest.raises((FrozenInstanceError, TypeError)):
        arguments.value = "invalid"


@pytest.mark.parametrize(
    ("overrides", "exception_type"),
    [
        ({"product_urls": cast(tuple[str, ...], [])}, TypeError),
        ({"product_urls": (1,)}, TypeError),
        ({"product_urls": ()}, ValueError),
        ({"state_file": cast(Path, "state.json")}, TypeError),
        ({"timeout_seconds": True}, TypeError),
        ({"timeout_seconds": cast(int, "10")}, TypeError),
        ({"timeout_seconds": 0}, ValueError),
        ({"price_drop_percentage": cast(Decimal, 1)}, TypeError),
        ({"price_drop_percentage": Decimal("NaN")}, ValueError),
        ({"price_drop_percentage": Decimal("-1")}, ValueError),
        ({"price_drop_percentage": Decimal("101")}, ValueError),
        ({"price_drop_amount": cast(Decimal, 1)}, TypeError),
        ({"price_drop_amount": Decimal("Infinity")}, ValueError),
        ({"price_drop_amount": Decimal("-0.01")}, ValueError),
    ],
)
def test_sync_arguments_reject_invalid_fields(
    overrides: dict[str, object],
    exception_type: type[Exception],
) -> None:
    values: dict[str, object] = {
        "product_urls": ("https://www.lidl.cz/tool/p100",),
        "state_file": Path("state.json"),
        "timeout_seconds": 10,
        "price_drop_percentage": None,
        "price_drop_amount": None,
    }
    values.update(overrides)

    with pytest.raises(exception_type):
        SyncArguments(**values)
