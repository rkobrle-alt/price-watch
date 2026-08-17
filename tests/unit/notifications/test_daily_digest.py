"""Tests for deterministic daily discount digest generation."""

import inspect
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from core.domain import Currency, Money, Percentage, Product, ProductId, ProviderId
from core.notifications import DailyDiscountDigest, DailyDiscountDigestEngine
from core.promotions import DailyPromotion
from core.state import StateSnapshot

_TIMESTAMP = datetime(2026, 8, 8, 6, 0, tzinfo=UTC)
_DATE = date(2026, 8, 8)
_PROVIDER_ID = ProviderId(UUID("018f0000-0000-7000-8000-000000000001"))


def _product(
    identifier: int,
    name: str,
    discount: str,
    *,
    available: bool = True,
    reference: str | None = "100.00",
) -> Product:
    return Product(
        id=ProductId(UUID(f"018f0000-0000-7000-8000-{identifier:012d}")),
        provider_id=_PROVIDER_ID,
        brand="PARKSIDE",
        name=name,
        current_price=Money(Decimal("80.00"), Currency.CZK),
        original_price=(
            None
            if reference is None
            else Money(Decimal(reference), Currency.CZK)
        ),
        discount_percent=Percentage(Decimal(discount)),
        url=f"https://example.test/{identifier}",
        image_url=None,
        created_at=_TIMESTAMP,
        availability=available,
    )


def _snapshot(product: Product) -> StateSnapshot:
    return StateSnapshot(product, _TIMESTAMP)


def test_engine_filters_orders_and_formats_qualifying_products() -> None:
    engine = DailyDiscountDigestEngine()
    products = (
        _product(4, "Unavailable", "80", available=False),
        _product(3, "No reference", "80", reference=None),
        _product(2, "beta", "20.00"),
        _product(5, "Below", "19.99"),
        _product(1, "Alpha", "30.00"),
        _product(6, "alpha", "20.00"),
    )

    digest = engine.generate(
        tuple(_snapshot(product) for product in products),
        Percentage(Decimal("20.00")),
        _DATE,
        _TIMESTAMP,
    )

    assert digest.products == (products[4], products[5], products[2])
    assert digest.calendar_date == _DATE
    assert digest.created_at == _TIMESTAMP
    assert digest.message == (
        "Parkside daily discount digest — 2026-08-08\n"
        "Minimum discount: 20.00%\n"
        "Discounted products: 3\n\n"
        "OSTATNÍ AKTUÁLNÍ SLEVY (3)\n\n"
        "1. Alpha\n"
        "Current price: 80.00 CZK\n"
        "Reference price: 100.00 CZK\n"
        "Discount: 30.00%\n"
        "URL: https://example.test/1\n\n"
        "2. alpha\n"
        "Current price: 80.00 CZK\n"
        "Reference price: 100.00 CZK\n"
        "Discount: 20.00%\n"
        "URL: https://example.test/6\n\n"
        "3. beta\n"
        "Current price: 80.00 CZK\n"
        "Reference price: 100.00 CZK\n"
        "Discount: 20.00%\n"
        "URL: https://example.test/2"
    )


def test_engine_marks_new_products_and_formats_separate_sections() -> None:
    products = (
        _product(1, "New drill", "30.00"),
        _product(2, "Existing battery", "25.00"),
        _product(3, "New charger", "20.00"),
    )

    digest = DailyDiscountDigestEngine().generate(
        tuple(_snapshot(product) for product in products),
        Percentage(Decimal("20.00")),
        _DATE,
        _TIMESTAMP,
        previous_product_ids=(products[1].id,),
    )

    assert digest.new_product_ids == (products[0].id, products[2].id)
    assert "🆕 NOVĚ VE SLEVĚ (2)\n\n1. New drill" in digest.message
    assert "\n\n2. New charger" in digest.message
    assert "OSTATNÍ AKTUÁLNÍ SLEVY (1)\n\n1. Existing battery" in (
        digest.message
    )


def test_absent_baseline_establishes_without_marking_products_new() -> None:
    product = _product(1, "Baseline drill", "30.00")

    digest = DailyDiscountDigestEngine().generate(
        (_snapshot(product),),
        Percentage(Decimal("20.00")),
        _DATE,
        _TIMESTAMP,
        previous_product_ids=None,
    )

    assert digest.new_product_ids == ()
    assert "NOVĚ VE SLEVĚ" not in digest.message
    assert "OSTATNÍ AKTUÁLNÍ SLEVY (1)" in digest.message


def test_empty_baseline_marks_every_qualifying_product_new() -> None:
    product = _product(1, "First new drill", "30.00")

    digest = DailyDiscountDigestEngine().generate(
        (_snapshot(product),),
        Percentage(Decimal("20.00")),
        _DATE,
        _TIMESTAMP,
        previous_product_ids=(),
    )

    assert digest.new_product_ids == (product.id,)
    assert "🆕 NOVĚ VE SLEVĚ (1)" in digest.message
    assert "OSTATNÍ AKTUÁLNÍ SLEVY" not in digest.message


def test_engine_generates_explicit_empty_digest() -> None:
    digest = DailyDiscountDigestEngine().generate(
        (), Percentage(Decimal("20")), _DATE, _TIMESTAMP
    )

    assert digest.products == ()
    assert digest.message == (
        "Parkside daily discount digest — 2026-08-08\n"
        "Minimum discount: 20%\n"
        "Discounted products: 0\n\n"
        "No currently available products match the discount threshold."
    )


def test_engine_formats_promotion_with_optional_url_in_every_digest() -> None:
    with_url = DailyPromotion(
        "Online | Today only",
        "https://www.lidl.cz/c/offer/s1",
    )
    promoted = DailyDiscountDigestEngine().generate(
        (),
        Percentage(Decimal("20")),
        _DATE,
        _TIMESTAMP,
        with_url,
    )
    without_url = DailyDiscountDigestEngine().generate(
        (),
        Percentage(Decimal("20")),
        _DATE,
        _TIMESTAMP,
        DailyPromotion("Weekend offer"),
    )

    assert promoted.promotion is with_url
    assert promoted.message.startswith(
        "Parkside daily discount digest — 2026-08-08\n"
        "Lidl daily offer: Online | Today only\n"
        "Offer URL: https://www.lidl.cz/c/offer/s1\n"
        "Minimum discount: 20%"
    )
    assert "Lidl daily offer: Weekend offer\nMinimum discount: 20%" in (
        without_url.message
    )

@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("calendar_date", _TIMESTAMP, TypeError),
        ("calendar_date", "2026-08-08", TypeError),
        ("created_at", "now", TypeError),
        ("created_at", datetime(2026, 8, 8), ValueError),
        ("products", [], TypeError),
        ("products", (object(),), TypeError),
        ("message", 1, TypeError),
        ("message", "  ", ValueError),
        ("promotion", object(), TypeError),
        ("new_product_ids", [], TypeError),
        ("new_product_ids", (object(),), TypeError),
    ],
)
def test_digest_rejects_invalid_values(
    field: str,
    value: object,
    error: type[Exception],
) -> None:
    values: dict[str, object] = {
        "calendar_date": _DATE,
        "created_at": _TIMESTAMP,
        "products": (),
        "message": "digest",
        "promotion": None,
        "new_product_ids": (),
    }
    values[field] = value

    with pytest.raises(error):
        DailyDiscountDigest(**values)  # type: ignore[arg-type]


def test_digest_rejects_duplicate_or_foreign_new_product_identifiers() -> None:
    product = _product(1, "Tool", "20")
    foreign = _product(2, "Other", "20")
    with pytest.raises(ValueError, match="unique"):
        DailyDiscountDigest(
            _DATE,
            _TIMESTAMP,
            (product,),
            "digest",
            new_product_ids=(product.id, product.id),
        )
    with pytest.raises(ValueError, match="digest products"):
        DailyDiscountDigest(
            _DATE,
            _TIMESTAMP,
            (product,),
            "digest",
            new_product_ids=(foreign.id,),
        )


@pytest.mark.parametrize(
    ("snapshots", "error", "match"),
    [
        ([], TypeError, "tuple"),
        ((object(),), TypeError, "StateSnapshot"),
    ],
)
def test_engine_rejects_invalid_snapshot_collections(
    snapshots: object,
    error: type[Exception],
    match: str,
) -> None:
    with pytest.raises(error, match=match):
        DailyDiscountDigestEngine().generate(  # type: ignore[arg-type]
            snapshots,
            Percentage(Decimal("20")),
            _DATE,
            _TIMESTAMP,
        )


def test_engine_rejects_duplicate_product_identifiers() -> None:
    snapshot = _snapshot(_product(1, "Tool", "20"))
    with pytest.raises(ValueError, match="unique"):
        DailyDiscountDigestEngine().generate(
            (snapshot, snapshot), Percentage(Decimal("20")), _DATE, _TIMESTAMP
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("minimum_discount", Decimal("20"), TypeError),
        ("calendar_date", _TIMESTAMP, TypeError),
        ("calendar_date", "today", TypeError),
        ("timestamp", "now", TypeError),
        ("timestamp", datetime(2026, 8, 8), ValueError),
        ("promotion", object(), TypeError),
        ("previous_product_ids", [], TypeError),
        ("previous_product_ids", (object(),), TypeError),
    ],
)
def test_engine_rejects_invalid_scalar_arguments(
    field: str,
    value: object,
    error: type[Exception],
) -> None:
    values: dict[str, object] = {
        "snapshots": (),
        "minimum_discount": Percentage(Decimal("20")),
        "calendar_date": _DATE,
        "timestamp": _TIMESTAMP,
        "promotion": None,
        "previous_product_ids": None,
    }
    values[field] = value
    with pytest.raises(error):
        DailyDiscountDigestEngine().generate(**values)  # type: ignore[arg-type]


def test_engine_rejects_duplicate_previous_product_identifiers() -> None:
    identifier = _product(1, "Tool", "20").id
    with pytest.raises(ValueError, match="unique"):
        DailyDiscountDigestEngine().generate(
            (),
            Percentage(Decimal("20")),
            _DATE,
            _TIMESTAMP,
            previous_product_ids=(identifier, identifier),
        )


def test_digest_public_objects_are_documented_and_immutable() -> None:
    digest = DailyDiscountDigest(_DATE, _TIMESTAMP, (), "digest")
    with pytest.raises(AttributeError):
        digest.message = "changed"  # type: ignore[misc]
    assert inspect.getdoc(DailyDiscountDigest)
    assert inspect.getdoc(DailyDiscountDigestEngine)
    assert inspect.signature(DailyDiscountDigestEngine.generate).return_annotation is (
        DailyDiscountDigest
    )
