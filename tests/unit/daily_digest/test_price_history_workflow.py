"""Historical context composes with current offers and reliable delivery."""

from datetime import time, timedelta
from decimal import Decimal

import pytest

from applications.daily_digest import DailyDigestWorkflow, DailyDigestConfig, DailyDigestStatus
from core.domain import Percentage
from core.notifications import DailyDiscountDigestEngine
from core.pricing import PriceHistoryEngine
from core.promotions import PromotionError
from tests.unit.daily_digest.test_workflow import _Reader, _Reservations, _Channel, _PromotionSource
from tests.unit.pricing.test_price_history import NOW, PRAGUE, observation, prior_days
from infrastructure.persistence.sqlite import SqliteDigestDeliveryStore


class Source:
    def __init__(self):
        self.calls = []
        self.result = None

    def assess(self, snapshots, timestamp):
        self.calls.append(snapshots)
        return tuple(PriceHistoryEngine(PRAGUE).assess(s, prior_days(), timestamp) for s in snapshots) if self.result is None else self.result


def workflow(source, channel, **extra):
    return DailyDigestWorkflow(_Reader((observation("80"),)), _Reservations(), DailyDiscountDigestEngine(), channel,
        DailyDigestConfig(time(8), Percentage(Decimal(20))), PRAGUE, price_history_source=source, **extra)


def test_history_source_is_not_called_for_already_reserved_date() -> None:
    source = Source()
    result = DailyDigestWorkflow(_Reader(), _Reservations(False), DailyDiscountDigestEngine(), _Channel(),
        DailyDigestConfig(time(8), Percentage(Decimal(20))), PRAGUE, price_history_source=source).run(NOW)
    assert result.status is DailyDigestStatus.ALREADY_SENT
    assert source.calls == []


def test_invalid_price_source_is_rejected() -> None:
    with pytest.raises(TypeError, match="price_history_source"):
        workflow(object(), _Channel())


def test_price_source_must_return_a_tuple() -> None:
    source = Source()
    source.result = []
    with pytest.raises(TypeError, match="return a tuple"):
        workflow(source, _Channel()).run(NOW)


def test_history_metadata_survives_banner_fallback_and_no_second_email(tmp_path) -> None:
    source, channel, promotion = Source(), _Channel(), _PromotionSource()
    promotion.error = PromotionError("banner unavailable")
    timestamp = NOW + timedelta(hours=1)
    # Keep the current offer recent so it can receive a supported value rating.
    reader = _Reader((observation("80", timestamp=timestamp),))
    current = DailyDigestWorkflow(reader, _Reservations(), DailyDiscountDigestEngine(), channel,
        DailyDigestConfig(time(8), Percentage(Decimal(20))), PRAGUE, price_history_source=source,
        promotion_source=promotion, delivery_store=SqliteDigestDeliveryStore(tmp_path / "db"))
    assert current.run(timestamp).status is DailyDigestStatus.SENT
    assert channel.digests[0].price_assessments
    assert "Dnešní akci Lidlu se nepodařilo ověřit" in channel.digests[0].message
    assert "Obvyklá cena" in channel.digests[0].message
    assert current.run(timestamp + timedelta(minutes=5)).status is DailyDigestStatus.ALREADY_SENT
    assert len(channel.digests) == 1
