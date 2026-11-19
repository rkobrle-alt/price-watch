"""Validate explicit delivery evidence and promotion fallback policy."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from core.notifications import DigestDeliveryRecord, DigestDeliveryPhase as Phase, DigestPromotionPolicy
from core.promotions import DailyPromotion
from applications.daily_digest import DailyDigestResult, DailyDigestStatus as Status
from tests.integration.test_reliable_digest_delivery import NOW, build
from tests.unit.homeassistant.test_digest_channel import _digest


@pytest.mark.parametrize(("field", "value", "exception"), [
    ("calendar_date", NOW, TypeError), ("calendar_date", "2026-11-19", TypeError),
    ("phase", "accepted", TypeError), ("updated_at", "now", TypeError),
    ("updated_at", datetime(2026, 11, 19), ValueError),
    ("product_count", True, TypeError), ("product_count", -1, ValueError),
    ("promotion_included", 1, TypeError), ("promotion_missing", 1, TypeError),
])
def test_delivery_record_rejects_invalid_evidence(field, value, exception) -> None:
    fields = dict(calendar_date=NOW.date(), phase=Phase.ACCEPTED, updated_at=NOW)
    fields[field] = value
    with pytest.raises(exception):
        DigestDeliveryRecord(**fields)


def test_contradictory_promotion_metadata_and_result_flags_are_rejected() -> None:
    with pytest.raises(ValueError):
        DigestDeliveryRecord(NOW.date(), Phase.ACCEPTED, NOW, promotion_included=True, promotion_missing=True)
    with pytest.raises(TypeError):
        DailyDigestResult(NOW.date(), Status.SENT, promotion_missing=1)
    with pytest.raises(ValueError):
        DailyDigestResult(NOW.date(), Status.NOT_DUE, promotion_missing=True)
    with pytest.raises(ValueError):
        DailyDigestResult(NOW.date(), Status.SENT, promotion_included=True, promotion_missing=True)


def test_banner_policy_validates_inputs_and_keeps_date_heading() -> None:
    policy = DigestPromotionPolicy()
    assert not policy.can_fallback(NOW + timedelta(minutes=29), NOW)
    assert policy.can_fallback(NOW + timedelta(minutes=30), NOW)
    with pytest.raises(TypeError):
        policy.can_fallback("now", NOW)
    with pytest.raises(ValueError):
        policy.can_fallback(NOW, datetime(2026, 11, 19))
    with pytest.raises(TypeError):
        policy.fallback_digest(object())
    with pytest.raises(ValueError):
        policy.fallback_digest(replace(_digest(), promotion=DailyPromotion("Offer")))
    assert policy.fallback_digest(_digest()).message.startswith("Daily digest\nDnešní akci")


def test_invalid_delivery_store_is_rejected(tmp_path) -> None:
    with pytest.raises(TypeError, match="delivery_store"):
        build(tmp_path / "db", store=object())
