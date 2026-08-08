"""Tests for deterministic reference-price enrichment."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import cast

import pytest

from core.domain import Currency, Money, Percentage, Product
from core.rules import PriceReferencePolicy
from core.state import StateSnapshot
from tests.unit.rules.helpers import TIMESTAMP, create_product


def _version(
    product: Product,
    amount: str,
    *,
    currency: Currency | None = None,
) -> Product:
    selected_currency = product.currency if currency is None else currency
    return replace(
        product,
        current_price=Money(Decimal(amount), selected_currency),
        original_price=None,
        discount_percent=Percentage(Decimal("0")),
    )


def test_provider_original_price_has_priority_and_recomputes_discount() -> None:
    current = create_product("80")
    current = replace(
        current,
        original_price=Money(Decimal("100"), Currency.CZK),
        discount_percent=Percentage(Decimal("1")),
    )
    historical = StateSnapshot(_version(current, "200"), TIMESTAMP)

    result = PriceReferencePolicy().enrich(current, (historical,))

    assert result.original_price == Money(Decimal("100"), Currency.CZK)
    assert result.discount_percent == Percentage(Decimal("20"))
    assert current.discount_percent == Percentage(Decimal("1"))


def test_historical_highest_same_currency_is_selected() -> None:
    current = create_product("75")
    history = (
        StateSnapshot(_version(current, "90"), TIMESTAMP),
        StateSnapshot(_version(current, "100"), TIMESTAMP + timedelta(hours=1)),
        StateSnapshot(
            _version(current, "1000", currency=Currency.EUR),
            TIMESTAMP + timedelta(hours=2),
        ),
    )

    result = PriceReferencePolicy().enrich(current, history)

    assert result.original_price == Money(Decimal("100"), Currency.CZK)
    assert result.discount_percent.value == Decimal("25")


def test_missing_reference_returns_same_product() -> None:
    current = create_product("75")

    assert PriceReferencePolicy().enrich(current, ()) is current


@pytest.mark.parametrize(
    ("reference", "current"),
    [("0", "0"), ("100", "100"), ("100", "110")],
)
def test_non_discount_reference_produces_zero_percentage(
    reference: str,
    current: str,
) -> None:
    product = create_product(current)
    product = replace(
        product,
        original_price=Money(Decimal(reference), Currency.CZK),
    )

    result = PriceReferencePolicy().enrich(product, ())

    assert result.discount_percent.value == Decimal("0")


@pytest.mark.parametrize("history", [[], (object(),)])
def test_invalid_history_types_are_rejected(history: object) -> None:
    with pytest.raises(TypeError, match="history"):
        PriceReferencePolicy().enrich(
            create_product("80"),
            cast(tuple[StateSnapshot, ...], history),
        )


def test_invalid_current_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="current"):
        PriceReferencePolicy().enrich(cast(Product, object()), ())


def test_history_for_another_product_is_rejected() -> None:
    current = create_product("80")
    other = create_product("100")

    with pytest.raises(ValueError, match="current product"):
        PriceReferencePolicy().enrich(
            current,
            (StateSnapshot(other, TIMESTAMP),),
        )
