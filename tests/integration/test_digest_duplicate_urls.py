"""Shared URLs do not crash digest preparation or rewrite product identities."""

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

from applications.daily_digest import DailyDigestConfig, DailyDigestStatus, DailyDigestWorkflow
from applications.homeassistant.composition import _LidlCatalogBatchSynchronizer
from applications.homeassistant.digest_refresh import _LidlDigestRefresher
from core.domain import Money, Percentage, ProductId
from core.notifications import DailyDiscountDigestEngine, NotificationEngine, PriceDropReservationPolicy
from core.rules import EvaluatorRegistry, PriceReferencePolicy, RuleEngine
from core.state import StateSnapshot
from infrastructure.persistence.sqlite import (
    SqliteDailyDigestBaselineStore, SqliteDailyDigestReservationStore,
    SqliteNotificationReservationStore, SqliteStateStore,
)
from infrastructure.providers.lidl import LidlParksideProvider
from infrastructure.providers.lidl.parser import parse_lidl_product
from tests.integration.test_daily_digest_baseline_restart import _Channel
from tests.unit.homeassistant_app.test_catalog_composition import _TextClient


def test_shared_url_is_fetched_once_and_digest_survives_restart(tmp_path: Path) -> None:
    timestamp = datetime(2026, 9, 14, 6, tzinfo=UTC)
    previous = timestamp - timedelta(days=1)
    url = "https://www.lidl.cz/p/parkside-test-tool/p100123456"
    page = _TextClient().get(url)
    current = parse_lidl_product(page, url, LidlParksideProvider.id, previous)
    old = replace(
        current, current_price=Money(Decimal("1500"), current.currency),
        original_price=Money(Decimal("2000"), current.currency),
        discount_percent=Percentage(Decimal("25")),
    )
    alias = replace(old, id=ProductId(uuid4()))
    path = tmp_path / "catalog.sqlite3"
    store = SqliteStateStore(path)
    store.save(StateSnapshot(old, previous))
    store.save(StateSnapshot(alias, previous))
    http = Mock()
    http.get.return_value = page
    individual_channel = Mock()
    synchronizer = _LidlCatalogBatchSynchronizer(
        http, lambda: timestamp, store, RuleEngine(EvaluatorRegistry()),
        NotificationEngine(), individual_channel, uuid4, store,
        PriceReferencePolicy(), SqliteNotificationReservationStore(path),
        PriceDropReservationPolicy(),
    )
    channel = _Channel()

    def compose() -> DailyDigestWorkflow:
        return DailyDigestWorkflow(
            SqliteStateStore(path), SqliteDailyDigestReservationStore(path),
            DailyDiscountDigestEngine(), channel,
            DailyDigestConfig(time(8), Percentage(Decimal("20"))),
            ZoneInfo("Europe/Prague"),
            baseline_store=SqliteDailyDigestBaselineStore(path),
            product_refresher=_LidlDigestRefresher(synchronizer),
        )

    result = compose().run(timestamp)
    assert result.status is DailyDigestStatus.SENT
    assert result.refresh_errors == ()
    http.get.assert_called_once_with(url)
    individual_channel.send.assert_not_called()
    assert len(channel.digests) == 1
    assert len(store.history(old.id)) == 2
    assert store.history(alias.id) == (StateSnapshot(alias, previous),)
    assert "Neověřeno v poslední hodině: 1" in channel.digests[0].message
    assert compose().run(timestamp).status is DailyDigestStatus.ALREADY_SENT
    assert len(channel.digests) == 1
    http.get.assert_called_once_with(url)
