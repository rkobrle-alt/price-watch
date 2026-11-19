"""Real read-only history analysis and durable daily delivery integration."""

import json
import sqlite3
import tracemalloc
from datetime import timedelta, time
from decimal import Decimal

import pytest

from applications.daily_digest import DailyDigestWorkflow, DailyDigestConfig, DailyDigestStatus
from core.domain import Percentage
from core.notifications import DailyDiscountDigestEngine, DigestDeliveryPhase
from core.pricing import PriceValueRating
from core.state import StateStoreError
from infrastructure.persistence.sqlite import SqlitePriceHistoryAssessmentSource, SqliteStateStore, SqliteDigestDeliveryStore, SqliteDailyDigestReservationStore
from infrastructure.persistence.snapshot_codec import encode_snapshot
from infrastructure.persistence.sqlite.database import SqlitePersistenceError
from tests.unit.daily_digest.test_workflow import _Channel
from tests.unit.pricing.test_price_history import NOW, PRAGUE, observation, prior_days
from tests.unit.persistence.sqlite_helpers import open_database


def test_history_is_read_only_and_appears_in_one_restart_safe_email(tmp_path) -> None:
    path = tmp_path / "db"
    store = SqliteStateStore(path)
    for snapshot in prior_days() + (observation("80"),):
        store.save(snapshot)
    channel = _Channel()
    def build():
        return DailyDigestWorkflow(
            store, SqliteDailyDigestReservationStore(path), DailyDiscountDigestEngine(), channel,
            DailyDigestConfig(time(8), Percentage(Decimal(20))), PRAGUE,
            delivery_store=SqliteDigestDeliveryStore(path),
            price_history_source=SqlitePriceHistoryAssessmentSource(path, PRAGUE),
        )
    source = SqlitePriceHistoryAssessmentSource(path, PRAGUE)
    before = path.read_bytes()
    result = source.assess((observation("80"),), NOW)
    assert path.read_bytes() == before
    assert result[0].rating is PriceValueRating.EXCELLENT
    assert build().run(NOW).status is DailyDigestStatus.SENT
    assert channel.digests[0].price_assessments[0] == result[0]
    assert "Obvyklá cena: 100.00 CZK" in channel.digests[0].message
    assert build().run(NOW + timedelta(minutes=5)).status is DailyDigestStatus.ALREADY_SENT
    assert len(channel.digests) == 1
    assert len(store.history(observation().product.id)) == 8


def test_source_streams_repeated_same_day_history_without_large_object_graph(tmp_path) -> None:
    path = tmp_path / "db"
    snapshot = observation("80")
    SqliteStateStore(path).save(snapshot)
    payload = json.dumps(encode_snapshot(snapshot))
    with open_database(path) as connection:
        connection.executemany("INSERT INTO observations(product_id, snapshot) VALUES (?, ?)", ((str(snapshot.product.id.value), payload) for _ in range(10000)))
        connection.commit()
    tracemalloc.start()
    try:
        result = SqlitePriceHistoryAssessmentSource(path, PRAGUE).assess((snapshot,), NOW)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result[0].observed_days_90 == 1
    assert peak < 2 * 1024 * 1024


@pytest.mark.parametrize(("snapshots", "timestamp", "error"), [
    ([], NOW, TypeError), ((object(),), NOW, TypeError),
    ((observation(), observation()), NOW, ValueError),
    ((), "now", TypeError), ((), NOW.replace(tzinfo=None), ValueError),
])
def test_source_validates_inputs(tmp_path, snapshots, timestamp, error) -> None:
    with pytest.raises(error):
        SqlitePriceHistoryAssessmentSource(tmp_path / "db", PRAGUE).assess(snapshots, timestamp)


def test_corrupted_history_fails_before_external_handoff(tmp_path) -> None:
    path = tmp_path / "db"
    store = SqliteStateStore(path)
    current = observation("80")
    store.save(current)
    with open_database(path) as connection:
        connection.execute("INSERT INTO observations(product_id, snapshot) VALUES (?, ?)", (str(current.product.id.value), "not-json"))
        connection.commit()
    channel = _Channel()
    from tests.unit.daily_digest.test_workflow import _Reader
    workflow = DailyDigestWorkflow(_Reader((current,)), SqliteDailyDigestReservationStore(path), DailyDiscountDigestEngine(), channel,
        DailyDigestConfig(time(8), Percentage(Decimal(20))), PRAGUE, delivery_store=SqliteDigestDeliveryStore(path),
        price_history_source=SqlitePriceHistoryAssessmentSource(path, PRAGUE))
    with pytest.raises(StateStoreError):
        workflow.run(NOW)
    assert channel.digests == []
    assert SqliteDigestDeliveryStore(path).latest().phase is DigestDeliveryPhase.READY


def test_source_wraps_open_query_and_close_failures(tmp_path, monkeypatch) -> None:
    path = tmp_path / "db"
    source = SqlitePriceHistoryAssessmentSource(path, PRAGUE)
    original = source._database.open
    def fail():
        raise SqlitePersistenceError("open failed")
    monkeypatch.setattr(source._database, "open", fail)
    with pytest.raises(StateStoreError, match="open"):
        source.assess((), NOW)
    monkeypatch.setattr(source._database, "open", original)
    class BadQuery(sqlite3.Connection):
        def execute(self, *args):
            raise sqlite3.OperationalError("query failed")
    monkeypatch.setattr(source._database, "open", lambda: sqlite3.connect(path, factory=BadQuery))
    with pytest.raises(StateStoreError, match="read"):
        source.assess((observation(),), NOW)
    monkeypatch.setattr(source._database, "open", original)
    close_original = source._database.close
    def close(connection):
        close_original(connection)
        raise SqlitePersistenceError("close failed")
    monkeypatch.setattr(source._database, "close", close)
    with pytest.raises(StateStoreError, match="close"):
        source.assess((), NOW)
