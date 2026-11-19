"""Daily weighting, calendar boundaries and conservative value ratings."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from core.domain import Money, Currency
from core.pricing import PriceHistoryEngine, PriceValueRating as Rating
from core.state import StateSnapshot
from tests.unit.notifications.test_daily_digest import _product

NOW = datetime(2026, 11, 19, 10, tzinfo=UTC)
PRAGUE = ZoneInfo("Europe/Prague")


def observation(amount="100", days=0, *, timestamp=None, available=True, currency=Currency.CZK, identifier=1):
    product = replace(_product(identifier, "Tool", "20"), current_price=Money(Decimal(amount), currency), original_price=Money(Decimal("100"), currency), availability=available)
    return StateSnapshot(product, timestamp or NOW - timedelta(days=days))


def prior_days(amount="100", count=7):
    return tuple(observation(amount, day) for day in range(1, count + 1))


@pytest.mark.parametrize(("current", "history", "expected"), [
    ("80", prior_days(), Rating.EXCELLENT),
    ("90", prior_days(), Rating.EXCELLENT),
    ("80", prior_days() + (observation("70", 10),), Rating.GOOD),
    ("95", prior_days(), Rating.LOWER),
    ("100", prior_days(), Rating.NORMAL),
    ("110", prior_days(), Rating.ABOVE_USUAL),
    ("80", prior_days(count=6), Rating.INSUFFICIENT_HISTORY),
    ("0", prior_days("0"), Rating.NORMAL),
    ("5", prior_days("0"), Rating.ABOVE_USUAL),
])
def test_ratings_compare_daily_median_and_recorded_minimum(current, history, expected) -> None:
    result = PriceHistoryEngine(PRAGUE).assess(observation(current), iter(history), NOW)
    assert result.rating is expected


def test_daily_median_ignores_request_frequency_but_minimum_retains_intraday_low() -> None:
    history = list(prior_days())
    repeated_time = NOW - timedelta(days=1, hours=1)
    history.extend(observation("1", timestamp=repeated_time) for _ in range(1000))
    history.append(observation("100", 1))
    result = PriceHistoryEngine(PRAGUE).assess(observation("80"), history, NOW)
    assert result.usual_price.amount == Decimal("100")
    assert result.minimum_30.amount == Decimal("1")
    assert result.prior_days == 7
    assert result.rating is Rating.GOOD
    assert result.saving_vs_usual_percent == Decimal("20")


def test_calendar_windows_ignore_foreign_currency_unavailable_and_future_prices() -> None:
    history = (
        observation("60", 29), observation("50", 30), observation("40", 89), observation("1", 90),
        observation("0", 1, currency=Currency.EUR), observation("0", 2, available=False),
        observation("0", timestamp=NOW + timedelta(seconds=1)),
    )
    result = PriceHistoryEngine(PRAGUE).assess(observation("80"), history, NOW)
    assert result.minimum_30.amount == Decimal("60")
    assert result.minimum_90.amount == Decimal("40")
    assert result.observed_days_30 == 2 and result.observed_days_90 == 4
    assert result.history_days == 91
    assert result.usual_price.amount == Decimal("50")


def test_timezone_rollover_and_out_of_order_daily_closes() -> None:
    asof = datetime(2026, 11, 18, 23, 30, tzinfo=UTC)  # Nov 19 in Prague.
    current = observation("80", timestamp=asof)
    history = (
        observation("120", timestamp=datetime(2026, 11, 17, 23, 30, tzinfo=UTC)),
        observation("100", timestamp=datetime(2026, 11, 18, 21, 0, tzinfo=UTC)),
        observation("150", timestamp=datetime(2026, 11, 17, 22, 0, tzinfo=UTC)),
        observation("90", timestamp=datetime(2026, 11, 18, 21, 0, tzinfo=UTC)),
    )
    result = PriceHistoryEngine(PRAGUE).assess(current, history, asof)
    assert result.usual_price.amount == Decimal("120")  # daily closes: 150 and 90.
    assert result.last_price_drop_on.isoformat() == "2026-11-19"
    assert result.history_days == 3


@pytest.mark.parametrize(("age", "expected"), [
    (timedelta(hours=1), Rating.EXCELLENT),
    (timedelta(hours=1, seconds=1), Rating.UNVERIFIED),
    (timedelta(seconds=-1), Rating.UNVERIFIED),
])
def test_one_hour_freshness_boundary(age, expected) -> None:
    result = PriceHistoryEngine(PRAGUE).assess(observation("80", timestamp=NOW - age), prior_days(), NOW)
    assert result.rating is expected


def test_empty_unavailable_history_and_decimal_median_are_truthful() -> None:
    engine = PriceHistoryEngine(PRAGUE)
    result = engine.assess(observation(available=False), (), NOW)
    assert result.history_days == 0 and result.first_observed_at is None
    assert result.minimum_30 is None and result.usual_price is None
    assert result.rating is Rating.UNVERIFIED
    result = engine.assess(observation("80"), (observation("100.01", 1), observation("100.02", 2)), NOW)
    assert result.usual_price.amount == Decimal("100.015")


@pytest.mark.parametrize(("current", "history", "timestamp", "error"), [
    (object(), (), NOW, TypeError), (observation(), None, NOW, TypeError),
    (observation(), (object(),), NOW, TypeError),
    (observation(), (observation(identifier=2),), NOW, ValueError),
    (observation(), (), "now", TypeError),
    (observation(), (), datetime(2026, 11, 19), ValueError),
])
def test_engine_rejects_invalid_evidence(current, history, timestamp, error) -> None:
    with pytest.raises(error):
        PriceHistoryEngine(PRAGUE).assess(current, history, timestamp)


def test_timezone_dependency_is_explicit() -> None:
    with pytest.raises(TypeError):
        PriceHistoryEngine("Europe/Prague")


def test_dst_fold_uses_absolute_time_for_daily_close_and_freshness() -> None:
    early = datetime(2026, 10, 25, 2, 45, tzinfo=PRAGUE, fold=0)
    later = datetime(2026, 10, 25, 2, 15, tzinfo=PRAGUE, fold=1)
    next_day = datetime(2026, 10, 26, 10, tzinfo=UTC)
    result = PriceHistoryEngine(PRAGUE).assess(observation("70", timestamp=next_day),
        (observation("80", timestamp=later), observation("100", timestamp=early)), next_day)
    assert result.usual_price.amount == Decimal("80")
    asof = datetime(2026, 10, 25, 2, 30, tzinfo=PRAGUE, fold=1)
    history = tuple(observation(timestamp=asof.astimezone(UTC) - timedelta(days=day)) for day in range(1, 8))
    result = PriceHistoryEngine(PRAGUE).assess(observation("80", timestamp=early), history, asof)
    assert result.rating is Rating.EXCELLENT
