"""Digest history evidence, stable novelty sections and mismatch rejection."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from core.domain import Percentage, Money
from core.notifications import DailyDiscountDigestEngine
from core.pricing import PriceHistoryEngine, PriceValueRating as Rating
from core.notifications.price_history_format import _format_price_history
from tests.unit.pricing.test_price_history import NOW, PRAGUE, observation, prior_days


def test_history_ranking_keeps_qualifying_set_and_new_membership() -> None:
    first = observation("80", identifier=1)
    second = observation("80", identifier=2)
    engine = PriceHistoryEngine(PRAGUE)
    insufficient = engine.assess(first, (), NOW)
    excellent = engine.assess(second, tuple(replace(s, product=replace(s.product, id=second.product.id)) for s in prior_days()), NOW)
    result = DailyDiscountDigestEngine().generate(
        (first, second), Percentage(Decimal(20)), NOW.date(), NOW,
        previous_product_ids=(first.product.id,), include_freshness=True,
        price_assessments=(insufficient, excellent),
    )
    assert result.products == (second.product, first.product)
    assert result.new_product_ids == (second.product.id,)
    assert result.price_assessments == (excellent, insufficient)
    assert "Minimum z pozorování za 30 dní: 80.00 CZK" in result.message
    assert "medián 7 předchozích denních cen" in result.message
    assert "Výborná cena vůči pozorované historii" in result.message
    assert "Nedostatek historie" in result.message
    assert "Dostupné období historie: 8 dní" in result.message
    assert "NOVĚ VE SLEVĚ" in result.message


@pytest.mark.parametrize("value", [[], (object(),)])
def test_digest_rejects_invalid_assessment_collections(value) -> None:
    with pytest.raises(TypeError):
        DailyDiscountDigestEngine().generate((observation(),), Percentage(Decimal(20)), NOW.date(), NOW, price_assessments=value)


@pytest.mark.parametrize("variant", ["duplicate", "missing", "price", "asof", "observed"])
def test_digest_rejects_mismatched_assessments(variant) -> None:
    snapshot = observation("80")
    assessment = PriceHistoryEngine(PRAGUE).assess(snapshot, prior_days(), NOW)
    values = (assessment,)
    if variant == "duplicate":
        values = (assessment, assessment)
    elif variant == "missing":
        values = ()
    elif variant == "price":
        values = (replace(assessment, current_price=Money(Decimal(81), snapshot.product.currency)),)
    elif variant == "asof":
        values = (replace(assessment, assessed_at=NOW + timedelta(seconds=1)),)
    else:
        values = (replace(assessment, observed_at=NOW - timedelta(seconds=1)),)
    with pytest.raises(ValueError):
        DailyDiscountDigestEngine().generate((snapshot,), Percentage(Decimal(20)), NOW.date(), NOW, price_assessments=values)


def test_empty_digest_and_sparse_unverified_history_use_honest_wording() -> None:
    result = DailyDiscountDigestEngine().generate((), Percentage(Decimal(20)), NOW.date(), NOW, price_assessments=())
    assert "Cenová historie" in result.message
    stale = observation("110", timestamp=NOW - timedelta(days=100))
    assessment = PriceHistoryEngine(PRAGUE).assess(stale, (), NOW)
    assert "není dostatek údajů" in _format_price_history(assessment)
    assert "výhodnost nehodnotíme" in _format_price_history(assessment)
    unavailable = PriceHistoryEngine(PRAGUE).assess(observation(available=False), (), NOW)
    assert "první záznam: není dostupné" in _format_price_history(unavailable)
    above = PriceHistoryEngine(PRAGUE).assess(observation("110"), prior_days(), NOW)
    assert "10.00 % nad" in _format_price_history(above)
