"""Missing-page filtering preserves history, retries and daily reservations."""

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from applications.daily_digest import DailyDigestConfig, DailyDigestStatus, DailyDigestWorkflow
from core.domain import Percentage, Product
from core.notifications import DailyDiscountDigestEngine
from core.provider import ProviderError, ProviderProductNotFoundError, ProviderTransportError
from core.state import StateSnapshot
from infrastructure.persistence.sqlite import SqliteDailyDigestBaselineStore, SqliteDailyDigestReservationStore, SqliteStateStore
from tests.integration.test_daily_digest_baseline_restart import _Channel, _PRODUCT_ONE, _PRODUCT_TWO, _save


class _Refresher:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.returned = False
        self.calls = 0

    def refresh(self, products: tuple[Product, ...], timestamp: datetime) -> tuple[ProviderError, ...]:
        self.calls += 1
        first = next(p for p in products if p.id == _PRODUCT_ONE)
        if self.returned:
            SqliteStateStore(self.path).save(StateSnapshot(replace(first, created_at=timestamp), timestamp))
            return ()
        return (ProviderProductNotFoundError("missing", first.url), ProviderTransportError("second offline"))


def test_missing_page_excluded_without_rewriting_history_and_can_return(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    now = datetime(2026, 11, 18, 7, tzinfo=UTC)
    old = now - timedelta(days=1)
    _save(path, _PRODUCT_ONE, old)
    _save(path, _PRODUCT_TWO, old)
    reader = SqliteStateStore(path)
    original = reader.latest_snapshots()
    channel, refresher = _Channel(), _Refresher(path)

    def compose() -> DailyDigestWorkflow:
        return DailyDigestWorkflow(
            SqliteStateStore(path), SqliteDailyDigestReservationStore(path),
            DailyDiscountDigestEngine(), channel,
            DailyDigestConfig(time(8), Percentage(Decimal("20"))), ZoneInfo("Europe/Prague"),
            baseline_store=SqliteDailyDigestBaselineStore(path), product_refresher=refresher,
        )

    result = compose().run(now)
    assert result.status is DailyDigestStatus.SENT
    assert len(result.refresh_errors) == 2
    assert tuple(p.id for p in channel.digests[0].products) == (_PRODUCT_TWO,)
    assert "NEOVĚŘENO V POSLEDNÍ HODINĚ" in channel.digests[0].message
    assert reader.latest_snapshots() == original
    assert len(reader.history(_PRODUCT_ONE)) == 1
    assert SqliteDailyDigestBaselineStore(path).previous_product_ids(now.date() + timedelta(days=1)) == (_PRODUCT_TWO,)
    assert compose().run(now).status is DailyDigestStatus.ALREADY_SENT
    assert refresher.calls == 1
    assert len(channel.digests) == 1

    refresher.returned = True
    assert compose().run(now + timedelta(days=1)).status is DailyDigestStatus.SENT
    assert {p.id for p in channel.digests[1].products} == {_PRODUCT_ONE, _PRODUCT_TWO}
    assert channel.digests[1].new_product_ids == (_PRODUCT_ONE,)
    assert len(reader.history(_PRODUCT_ONE)) == 2
