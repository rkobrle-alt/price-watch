"""Verify preflight ordering, updated snapshots and failure compensation."""

from dataclasses import replace
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import cast

import pytest

from applications.daily_digest import DailyDigestConfig, DailyDigestResult, DailyDigestStatus, DailyDigestWorkflow
from core.domain import Percentage, Product
from core.notifications import DailyDiscountDigestEngine, DigestProductRefresher
from core.promotions import PromotionError
from core.provider import ProviderError, ProviderTransportError
from core.state import StateSnapshot, StateStoreError
from tests.unit.daily_digest.test_workflow import _Reader, _Reservations, _Channel, _Baselines, _PromotionSource, _PRAGUE, _TIMESTAMP, _DATE
from tests.unit.notifications.test_daily_digest import _product


class _Refresher:
    def __init__(self, reader: _Reader, baseline: _Baselines) -> None:
        self.reader = reader
        self.baseline = baseline
        self.calls: list[tuple[Product, ...]] = []
        self.error: Exception | None = None
        self.result: object = ()
        self.updated: tuple[StateSnapshot, ...] = ()

    def refresh(self, products: tuple[Product, ...], timestamp: datetime) -> tuple[ProviderError, ...]:
        assert self.baseline.stage_calls == []
        assert timestamp == _TIMESTAMP
        self.calls.append(products)
        if self.error is not None:
            raise self.error
        self.reader.snapshots = self.updated
        return cast(tuple[ProviderError, ...], self.result)


def _build(refresher: object, reader: _Reader, reservations: _Reservations, baseline: _Baselines, channel: _Channel, source: _PromotionSource | None = None) -> DailyDigestWorkflow:
    return DailyDigestWorkflow(reader, reservations, DailyDiscountDigestEngine(), channel,
        DailyDigestConfig(time(8), Percentage(Decimal("20"))), _PRAGUE,
        baseline_store=baseline, promotion_source=source,
        product_refresher=cast(DigestProductRefresher, refresher))


def test_refresh_reloads_prices_stock_and_retains_honest_stale_warning() -> None:
    products = tuple(_product(i, f"Tool {i}", "20") for i in range(1, 5))
    old = tuple(StateSnapshot(p, _TIMESTAMP - timedelta(days=1)) for p in products)
    reader, baseline, channel, reservations = _Reader(old), _Baselines(()), _Channel(), _Reservations()
    refresher = _Refresher(reader, baseline)
    error = ProviderTransportError("offline")
    refresher.result = (error,)
    refresher.updated = (
        StateSnapshot(replace(products[0], availability=False), _TIMESTAMP),
        StateSnapshot(replace(products[1], discount_percent=Percentage(Decimal("10"))), _TIMESTAMP),
        StateSnapshot(products[2], _TIMESTAMP), old[3],
    )
    result = _build(refresher, reader, reservations, baseline, channel).run(_TIMESTAMP)
    assert refresher.calls == [products]
    assert reader.calls == 2
    assert result.refresh_errors == (error,)
    assert channel.digests[0].products == products[2:]
    assert "Neověřeno v poslední hodině: 1" in channel.digests[0].message
    assert baseline.stage_calls == [(_DATE, tuple(p.id for p in products[2:]))]


@pytest.mark.parametrize("reason", ["not_due", "already_sent", "promotion"])
def test_ineligible_or_failed_promotion_does_not_refresh(reason: str) -> None:
    reader, baseline, channel = _Reader(), _Baselines(), _Channel()
    reservations = _Reservations(reason != "already_sent")
    source = _PromotionSource()
    if reason == "promotion":
        source.error = PromotionError("offline")
    refresher = _Refresher(reader, baseline)
    timestamp = _TIMESTAMP - timedelta(minutes=1) if reason == "not_due" else _TIMESTAMP
    _build(refresher, reader, reservations, baseline, channel, source).run(timestamp)
    assert refresher.calls == []
    assert reader.calls == 0


@pytest.mark.parametrize("failure", [RuntimeError("failed"), StateStoreError("disk failed"), [], (object(),)])
def test_refresher_failure_or_contract_violation_releases_reservation(failure: object) -> None:
    reader, baseline, channel, reservations = _Reader(), _Baselines(), _Channel(), _Reservations()
    refresher = _Refresher(reader, baseline)
    if isinstance(failure, Exception):
        refresher.error = failure
    else:
        refresher.result = failure
    with pytest.raises((RuntimeError, TypeError, StateStoreError)):
        _build(refresher, reader, reservations, baseline, channel).run(_TIMESTAMP)
    assert reservations.release_calls == [_DATE]
    assert baseline.release_calls == [_DATE]
    assert channel.digests == []


def test_invalid_refresher_and_result_errors_rejected() -> None:
    with pytest.raises(TypeError, match="product_refresher"):
        _build(object(), _Reader(), _Reservations(), _Baselines(), _Channel())
    for errors in ([], (object(),)):
        with pytest.raises(TypeError, match="refresh_errors"):
            DailyDigestResult(_DATE, DailyDigestStatus.SENT, refresh_errors=errors)
    with pytest.raises(ValueError, match="non-delivery"):
        DailyDigestResult(_DATE, DailyDigestStatus.NOT_DUE, refresh_errors=(ProviderError("offline"),))
