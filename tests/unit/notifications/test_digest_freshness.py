"""Freshness boundaries, deterministic priorities and honest email evidence."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from core.domain import Percentage
from core.notifications import DailyDiscountDigestEngine, DigestFreshnessPolicy
from core.state import StateSnapshot
from tests.unit.notifications.test_daily_digest import _DATE, _TIMESTAMP, _product


def test_priority_filters_qualification_and_recent_data_then_caps_oldest() -> None:
    products = tuple(_product(i, f"Tool {i}", "20") for i in range(1, 7))
    ages = (timedelta(hours=3), timedelta(hours=2), timedelta(hours=2),
            timedelta(hours=1), timedelta(0), timedelta(seconds=-1))
    snapshots = tuple(StateSnapshot(p, _TIMESTAMP - age) for p, age in zip(products, ages))
    excluded = (
        StateSnapshot(_product(7, "Below", "19"), _TIMESTAMP - timedelta(days=1)),
        StateSnapshot(_product(8, "Unavailable", "50", available=False), _TIMESTAMP - timedelta(days=1)),
        StateSnapshot(_product(9, "No reference", "50", reference=None), _TIMESTAMP - timedelta(days=1)),
    )
    policy = DigestFreshnessPolicy()
    threshold = Percentage(Decimal("20"))
    assert policy.select(tuple(reversed(snapshots)) + excluded, threshold, _TIMESTAMP, 2) == products[:2]
    assert policy.select(snapshots, threshold, _TIMESTAMP) == (products[0], products[1], products[2], products[5])
    assert policy.select((), threshold, _TIMESTAMP) == ()


@pytest.mark.parametrize("limit,error", [(True, TypeError), ("2", TypeError), (0, ValueError), (-1, ValueError)])
def test_priority_rejects_invalid_limits(limit: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        DigestFreshnessPolicy().select((), Percentage(Decimal("20")), _TIMESTAMP, cast(int, limit))


@pytest.mark.parametrize("timestamp,error", [("now", TypeError), (_TIMESTAMP.replace(tzinfo=None), ValueError)])
def test_priority_rejects_invalid_time(timestamp: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        DigestFreshnessPolicy().select((), Percentage(Decimal("20")), cast(datetime, timestamp))


def test_priority_default_budget_is_two_hundred() -> None:
    snapshots = tuple(StateSnapshot(_product(i, "Tool", "20"), _TIMESTAMP - timedelta(days=1)) for i in range(1, 202))
    assert len(DigestFreshnessPolicy().select(snapshots, Percentage(Decimal("20")), _TIMESTAMP)) == 200


def test_email_reports_actual_observation_times_and_recent_counts() -> None:
    ages = (timedelta(hours=1), timedelta(hours=1, microseconds=1), timedelta(seconds=-1), timedelta(0))
    snapshots = tuple(StateSnapshot(_product(i, f"Tool {i}", "20"), _TIMESTAMP - age) for i, age in enumerate(ages, 1))
    digest = DailyDiscountDigestEngine().generate(
        snapshots, Percentage(Decimal("20")), _DATE, _TIMESTAMP,
        previous_product_ids=(snapshots[1].product.id,), include_freshness=True,
    )
    assert "Ověřeno v poslední hodině: 2" in digest.message
    assert "Neověřeno v poslední hodině: 2" in digest.message
    assert digest.message.count("NEOVĚŘENO V POSLEDNÍ HODINĚ") == 2
    assert "🆕 NOVĚ VE SLEVĚ (3)" in digest.message
    assert "OSTATNÍ AKTUÁLNÍ SLEVY (1)" in digest.message
    for snapshot in snapshots:
        assert f"Poslední úspěšná kontrola: {snapshot.timestamp.isoformat()}" in digest.message
    assert digest == DailyDiscountDigestEngine().generate(
        snapshots, Percentage(Decimal("20")), _DATE, _TIMESTAMP,
        previous_product_ids=(snapshots[1].product.id,), include_freshness=True,
    )


def test_empty_freshness_digest_and_invalid_flag() -> None:
    engine = DailyDiscountDigestEngine()
    digest = engine.generate((), Percentage(Decimal("20")), _DATE, _TIMESTAMP, include_freshness=True)
    assert "Neověřeno v poslední hodině: 0" in digest.message
    assert "No currently available products" in digest.message
    with pytest.raises(TypeError, match="include_freshness"):
        engine.generate((), Percentage(Decimal("20")), _DATE, _TIMESTAMP, include_freshness=cast(bool, 1))
