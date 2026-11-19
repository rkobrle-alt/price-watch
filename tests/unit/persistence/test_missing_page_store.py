"""Schema migration and failure atomicity for missing-page evidence."""

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from core.catalog import CatalogStoreError, MissingPagePolicy
from infrastructure.persistence.sqlite import SqliteMissingProductPageStore, SqliteStateStore, SqliteDailyDigestReservationStore
from infrastructure.persistence.sqlite.database import SqlitePersistenceError
from tests.unit.persistence.sqlite_helpers import CATALOG_PROVIDER_ID, open_database
from tests.unit.persistence.helpers import create_snapshot
from tests.integration.test_missing_page_lifecycle import NOW


def test_schema_seven_migration_preserves_history_and_reservations(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    snapshot = create_snapshot()
    SqliteStateStore(path).save(snapshot)
    reservation = SqliteDailyDigestReservationStore(path)
    assert reservation.reserve(NOW.date(), NOW)
    with open_database(path) as connection:
        connection.execute("DROP TABLE missing_product_pages")
        connection.execute("PRAGMA user_version = 7")
        connection.commit()
    store = SqliteMissingProductPageStore(path)
    assert store.load() == ()
    assert SqliteStateStore(path).history(snapshot.product.id) == (snapshot,)
    assert not reservation.reserve(NOW.date(), NOW)
    page = MissingPagePolicy().record(CATALOG_PROVIDER_ID, "url", NOW)
    store.save((page,))
    assert SqliteMissingProductPageStore(path).load() == (page,)
    store.save(())
    assert store.load() == ()


@pytest.mark.parametrize("pages", [[], (object(),)])
def test_store_rejects_invalid_values(tmp_path: Path, pages: object) -> None:
    with pytest.raises(TypeError):
        SqliteMissingProductPageStore(tmp_path / "db").save(pages)


def test_store_rejects_duplicate_keys(tmp_path: Path) -> None:
    page = MissingPagePolicy().record(CATALOG_PROVIDER_ID, "url", NOW)
    with pytest.raises(ValueError, match="unique"):
        SqliteMissingProductPageStore(tmp_path / "db").save((page, page))


@pytest.mark.parametrize("method", ["load", "save"])
def test_open_failure_is_wrapped(tmp_path: Path, monkeypatch, method: str) -> None:
    store = SqliteMissingProductPageStore(tmp_path / "db")
    def fail():
        raise SqlitePersistenceError("open failed")
    monkeypatch.setattr(store._database, "open", fail)
    with pytest.raises(CatalogStoreError):
        getattr(store, method)(*(((),) if method == "save" else ()))


def test_corruption_and_close_failures_are_wrapped(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "db"
    store = SqliteMissingProductPageStore(path)
    store.load()
    with open_database(path) as connection:
        connection.execute("INSERT INTO missing_product_pages VALUES ('invalid', 'url', 1, 'bad', 'bad')")
        connection.commit()
    with pytest.raises(CatalogStoreError, match="read"):
        store.load()
    original = store._database.close
    def close(connection):
        original(connection)
        raise SqlitePersistenceError("close failed")
    monkeypatch.setattr(store._database, "close", close)
    with pytest.raises(CatalogStoreError, match="close"):
        store.save(())


def test_save_transaction_failure_preserves_previous_rows(tmp_path: Path) -> None:
    path = tmp_path / "db"
    store = SqliteMissingProductPageStore(path)
    page = MissingPagePolicy().record(CATALOG_PROVIDER_ID, "url", NOW)
    store.save((page,))
    with open_database(path) as connection:
        connection.execute("CREATE TRIGGER reject_page BEFORE INSERT ON missing_product_pages BEGIN SELECT RAISE(ABORT, 'fail'); END")
        connection.commit()
    with pytest.raises(CatalogStoreError, match="save"):
        store.save((page,))
    assert store.load() == (page,)


def test_schema_migration_failure_does_not_advance_version(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "db"
    store = SqliteMissingProductPageStore(path)
    store.load()
    with open_database(path) as connection:
        connection.execute("DROP TABLE missing_product_pages")
        connection.execute("PRAGMA user_version = 7")
        connection.commit()
    def fail(connection):
        connection.execute("CREATE TABLE missing_product_pages (wrong TEXT)")
        raise sqlite3.OperationalError("failed")
    monkeypatch.setattr("infrastructure.persistence.sqlite.database._create_missing_page_table", fail)
    with pytest.raises(CatalogStoreError):
        store.load()
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='missing_product_pages'").fetchone() is None


def test_wrong_missing_page_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "db"
    store = SqliteMissingProductPageStore(path)
    store.load()
    with open_database(path) as connection:
        connection.execute("DROP TABLE missing_product_pages")
        connection.execute("CREATE TABLE missing_product_pages (wrong TEXT)")
        connection.commit()
    with pytest.raises(CatalogStoreError):
        store.load()
