"""Ledger atomicity, migration and malformed-data behavior."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from core.notifications import DailyDigestReservationError, DigestDeliveryPhase as Phase
from infrastructure.persistence.sqlite import SqliteDigestDeliveryStore, SqliteStateStore, SqliteDailyDigestReservationStore, SqliteDailyDigestBaselineStore
from infrastructure.persistence.sqlite.database import SqlitePersistenceError
from tests.integration.test_reliable_digest_delivery import NOW
from tests.unit.persistence.sqlite_helpers import open_database
from tests.unit.persistence.helpers import create_snapshot


def test_migration_preserves_history_and_legacy_date_without_asserting_acceptance(tmp_path) -> None:
    path = tmp_path / "db"
    snapshot = create_snapshot()
    SqliteStateStore(path).save(snapshot)
    reservations = SqliteDailyDigestReservationStore(path)
    reservations.reserve(NOW.date(), NOW)
    with open_database(path) as connection:
        connection.execute("DROP TABLE digest_delivery_attempts")
        connection.execute("PRAGMA user_version=8")
        connection.commit()
    store = SqliteDigestDeliveryStore(path)
    assert store.latest().phase is Phase.LEGACY_RESERVED
    assert store.claim(NOW.date(), NOW) is Phase.LEGACY_RESERVED
    assert SqliteStateStore(path).history(snapshot.product.id) == (snapshot,)
    assert not reservations.reserve(NOW.date(), NOW)
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (9,)


def test_claim_compare_transition_and_baseline_visibility(tmp_path) -> None:
    path = tmp_path / "db"
    store = SqliteDigestDeliveryStore(path)
    assert store.latest() is None
    store.recover(NOW)
    assert store.claim(NOW.date(), NOW) is Phase.PREPARING
    assert store.claim(NOW.date(), NOW) is Phase.PREPARING
    baseline = SqliteDailyDigestBaselineStore(path)
    baseline.stage(NOW.date(), ())
    assert baseline.previous_product_ids(NOW.date() + timedelta(days=1)) is None
    store.transition(NOW.date(), Phase.PREPARING, Phase.SENDING, NOW, product_count=3)
    assert store.claim(NOW.date(), NOW) is Phase.SENDING
    store.transition(NOW.date(), Phase.SENDING, Phase.ACCEPTED, NOW, product_count=3)
    assert baseline.previous_product_ids(NOW.date() + timedelta(days=1)) == ()
    assert store.latest().product_count == 3
    assert store.claim(NOW.date(), NOW) is Phase.ACCEPTED
    with pytest.raises(DailyDigestReservationError):
        store.transition(NOW.date(), Phase.SENDING, Phase.READY, NOW)
    with pytest.raises(DailyDigestReservationError):
        store.transition(NOW.date() + timedelta(days=1), Phase.PREPARING, Phase.SENDING, NOW)


def test_recovery_releases_abandoned_candidate_and_preserves_uncertain_reservation(tmp_path) -> None:
    path = tmp_path / "db"
    store = SqliteDigestDeliveryStore(path)
    first, second = NOW.date(), NOW.date() + timedelta(days=1)
    store.claim(first, NOW)
    store.claim(second, NOW)
    store.transition(second, Phase.PREPARING, Phase.SENDING, NOW)
    store.recover(NOW + timedelta(minutes=5))
    assert store.claim(first, NOW + timedelta(minutes=5)) is Phase.PREPARING
    assert store.claim(second, NOW + timedelta(minutes=5)) is Phase.UNCERTAIN


def test_public_arguments_and_transition_chronology_are_validated(tmp_path) -> None:
    store = SqliteDigestDeliveryStore(tmp_path / "db")
    with pytest.raises(TypeError):
        store.recover("now")
    with pytest.raises(ValueError):
        store.recover(datetime(2026, 1, 1))
    with pytest.raises(TypeError):
        store.claim(NOW, NOW)
    with pytest.raises(TypeError):
        store.transition(NOW.date(), "preparing", Phase.SENDING, NOW)
    with pytest.raises(ValueError):
        store.transition(NOW.date(), Phase.READY, Phase.ACCEPTED, NOW)
    store.claim(NOW.date(), NOW)
    with pytest.raises(DailyDigestReservationError):
        store.recover(NOW - timedelta(seconds=1))
    with pytest.raises(DailyDigestReservationError):
        store.claim(NOW.date(), NOW - timedelta(seconds=1))
    with pytest.raises(DailyDigestReservationError):
        store.transition(NOW.date(), Phase.PREPARING, Phase.SENDING, NOW - timedelta(seconds=1))


@pytest.mark.parametrize(("column", "value"), [
    ("phase", "invalid"), ("calendar_date", "20261119"),
    ("updated_at", "2026-11-19 07:00:00+00:00"), ("updated_at", "bad"),
    ("promotion_included", 3), ("promotion_missing", 3),
    ("product_count", -1),
])
def test_corrupt_evidence_is_not_treated_as_permission_to_send(tmp_path, column, value) -> None:
    path = tmp_path / "db"
    store = SqliteDigestDeliveryStore(path)
    store.claim(NOW.date(), NOW)
    with open_database(path) as connection:
        connection.execute(f"UPDATE digest_delivery_attempts SET {column}=?", (value,))
        connection.commit()
    with pytest.raises(DailyDigestReservationError):
        store.latest()


def test_open_and_close_failures_are_wrapped(tmp_path, monkeypatch) -> None:
    store = SqliteDigestDeliveryStore(tmp_path / "db")
    original = store._database.open
    def fail():
        raise SqlitePersistenceError("open failed")
    monkeypatch.setattr(store._database, "open", fail)
    with pytest.raises(DailyDigestReservationError):
        store.latest()
    monkeypatch.setattr(store._database, "open", original)
    close_original = store._database.close
    def close(connection):
        close_original(connection)
        raise SqlitePersistenceError("close failed")
    monkeypatch.setattr(store._database, "close", close)
    with pytest.raises(DailyDigestReservationError, match="close"):
        store.latest()


def test_failed_migration_rolls_back_table_and_version(tmp_path, monkeypatch) -> None:
    path = tmp_path / "db"
    store = SqliteDigestDeliveryStore(path)
    store.latest()
    with open_database(path) as connection:
        connection.execute("DROP TABLE digest_delivery_attempts")
        connection.execute("PRAGMA user_version=8")
        connection.commit()
    def fail(connection):
        connection.execute("CREATE TABLE digest_delivery_attempts (wrong TEXT)")
        raise sqlite3.OperationalError("failed")
    monkeypatch.setattr("infrastructure.persistence.sqlite.database._create_digest_delivery_table", fail)
    with pytest.raises(DailyDigestReservationError):
        store.latest()
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (8,)
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='digest_delivery_attempts'").fetchone() is None


def test_malformed_delivery_table_is_rejected(tmp_path) -> None:
    path = tmp_path / "db"
    store = SqliteDigestDeliveryStore(path)
    store.latest()
    with open_database(path) as connection:
        connection.execute("DROP TABLE digest_delivery_attempts")
        connection.execute("CREATE TABLE digest_delivery_attempts (wrong TEXT)")
        connection.commit()
    with pytest.raises(DailyDigestReservationError):
        store.latest()


def test_process_interruption_before_database_open_preserves_termination(tmp_path, monkeypatch) -> None:
    store = SqliteDigestDeliveryStore(tmp_path / "db")
    def interrupt():
        raise KeyboardInterrupt()
    monkeypatch.setattr(store._database, "open", interrupt)
    with pytest.raises(KeyboardInterrupt):
        store.latest()
