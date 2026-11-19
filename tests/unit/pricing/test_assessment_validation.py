"""Explicit public evidence contracts and invalid aggregate inputs."""

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

import core.pricing as pricing
from core.domain import Money, Currency
from core.pricing import PriceHistoryEngine
from tests.unit.pricing.test_price_history import NOW, PRAGUE, observation, prior_days


@pytest.mark.parametrize(("field", "value", "exception"), [
    ("product_id", "id", TypeError), ("current_price", 1, TypeError), ("rating", "good", TypeError),
    ("observed_at", "now", TypeError), ("assessed_at", datetime(2026, 11, 19), ValueError),
    ("first_observed_at", NOW + timedelta(seconds=1), ValueError),
    ("history_days", True, TypeError), ("history_days", -1, ValueError),
    ("observed_days_30", 31, ValueError), ("observed_days_90", 91, ValueError),
    ("prior_days", 90, ValueError), ("first_observed_at", None, ValueError),
    ("minimum_30", 5, TypeError), ("usual_price", Money(Decimal(1), Currency.EUR), ValueError),
    ("saving_vs_usual_percent", 1.0, TypeError), ("saving_vs_usual_percent", Decimal("NaN"), ValueError),
    ("last_price_drop_on", NOW, TypeError), ("last_price_drop_on", "2026-11-19", TypeError),
])
def test_invalid_aggregate_evidence_is_rejected(field, value, exception) -> None:
    assessment = PriceHistoryEngine(PRAGUE).assess(observation("80"), prior_days(), NOW)
    with pytest.raises(exception):
        replace(assessment, **{field: value})


def test_pricing_public_api_is_explicit_and_documented() -> None:
    assert pricing.__all__ == ["PriceHistoryAssessment", "PriceValueRating", "PriceHistoryEngine", "PriceHistoryAssessmentSource"]
    for name in pricing.__all__:
        assert getattr(pricing, name).__doc__
