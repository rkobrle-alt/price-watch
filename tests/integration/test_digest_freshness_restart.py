"""Fresh digest observations, history and reservations survive SQLite restart."""

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from applications.daily_digest import DailyDigestConfig, DailyDigestStatus, DailyDigestWorkflow
from core.domain import Percentage, Product
from core.notifications import DailyDiscountDigestEngine
from core.provider import ProviderError
from core.state import StateSnapshot
from infrastructure.persistence.sqlite import (
    SqliteDailyDigestBaselineStore, SqliteDailyDigestReservationStore, SqliteStateStore,
)
from tests.integration.test_daily_digest_baseline_restart import (
    _Channel, _PRODUCT_ONE, _PRODUCT_TWO, _save,
)


class _Refresher:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.calls: list[tuple[Product, ...]] = []

    def refresh(
        self, products: tuple[Product, ...], timestamp: datetime,
    ) -> tuple[ProviderError, ...]:
        self.calls.append(products)
        for product in products:
            if product.id == _PRODUCT_ONE:
                SqliteStateStore(self.path).save(
                    StateSnapshot(replace(product, availability=False), timestamp)
                )
        return (ProviderError("second product offline"),)


def test_refresh_persists_history_and_final_baseline_without_resending_after_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    timestamp = datetime(2026, 9, 8, 6, tzinfo=UTC)
    previous = timestamp - timedelta(days=1)
    _save(path, _PRODUCT_ONE, previous)
    _save(path, _PRODUCT_TWO, previous)
    channel = _Channel()
    refresher = _Refresher(path)

    def compose() -> DailyDigestWorkflow:
        return DailyDigestWorkflow(
            SqliteStateStore(path), SqliteDailyDigestReservationStore(path),
            DailyDiscountDigestEngine(), channel,
            DailyDigestConfig(time(8), Percentage(Decimal("20"))),
            ZoneInfo("Europe/Prague"),
            baseline_store=SqliteDailyDigestBaselineStore(path),
            product_refresher=refresher,
        )

    result = compose().run(timestamp)
    assert result.status is DailyDigestStatus.SENT
    assert len(result.refresh_errors) == 1
    assert tuple(product.id for product in channel.digests[0].products) == (_PRODUCT_TWO,)
    assert "NEOVĚŘENO V POSLEDNÍ HODINĚ" in channel.digests[0].message
    assert previous.isoformat() in channel.digests[0].message
    assert len(SqliteStateStore(path).history(_PRODUCT_ONE)) == 2
    assert len(SqliteStateStore(path).history(_PRODUCT_TWO)) == 1
    assert SqliteDailyDigestBaselineStore(path).previous_product_ids(
        timestamp.date() + timedelta(days=1)
    ) == (_PRODUCT_TWO,)

    assert compose().run(timestamp).status is DailyDigestStatus.ALREADY_SENT
    assert len(refresher.calls) == 1
    assert len(channel.digests) == 1
