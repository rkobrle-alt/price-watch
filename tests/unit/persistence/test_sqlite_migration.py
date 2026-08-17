"""Tests for the transactional SQLite schema 1 to 2 migration."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.catalog import CatalogStoreError
from infrastructure.persistence.snapshot_codec import encode_snapshot
from infrastructure.persistence.sqlite import SqliteCatalogStore, SqliteStateStore
from infrastructure.persistence.sqlite.database import SqlitePersistenceError
from tests.unit.persistence.helpers import PRODUCT_ID, create_snapshot
from tests.unit.persistence.sqlite_helpers import (
    CATALOG_PROVIDER_ID,
    create_reference,
    open_database,
)

_NOW = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
_V1_CATALOG_COLUMNS = (
    "sequence",
    "provider_id",
    "external_id",
    "url",
    "first_seen_at",
    "last_seen_at",
)


def _create_version_one_database(
    path: Path,
    *,
    conflicting_index: bool = False,
) -> None:
    reference = create_reference("p1")
    snapshot = create_snapshot()
    with open_database(path) as connection:
        connection.execute(
            "CREATE TABLE catalog_entries ("
            "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
            "provider_id TEXT NOT NULL, external_id TEXT NOT NULL, "
            "url TEXT NOT NULL, first_seen_at TEXT NOT NULL, "
            "last_seen_at TEXT NOT NULL, "
            "UNIQUE(provider_id, external_id))"
        )
        connection.execute(
            "CREATE TABLE observations ("
            "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
            "product_id TEXT NOT NULL, snapshot TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX observations_product_sequence "
            "ON observations(product_id, sequence)"
        )
        if conflicting_index:
            connection.execute(
                "CREATE INDEX catalog_refresh_order ON observations(sequence)"
            )
        connection.execute(
            "INSERT INTO catalog_entries (provider_id, external_id, url, "
            "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
            (
                str(reference.provider_id.value),
                reference.external_id,
                reference.url,
                _NOW.isoformat(),
                _NOW.isoformat(),
            ),
        )
        connection.execute(
            "INSERT INTO observations (product_id, snapshot) VALUES (?, ?)",
            (
                str(snapshot.product.id.value),
                json.dumps(
                    encode_snapshot(snapshot),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()


def _create_version_two_database(
    path: Path,
    *,
    conflicting_table: bool = False,
) -> None:
    _create_version_one_database(path)
    with open_database(path) as connection:
        connection.execute(
            "ALTER TABLE catalog_entries "
            "ADD COLUMN last_refresh_attempt_at TEXT"
        )
        connection.execute(
            "CREATE INDEX catalog_refresh_order ON catalog_entries("
            "provider_id, last_refresh_attempt_at, sequence)"
        )
        if conflicting_table:
            connection.execute(
                "CREATE TABLE notification_reservations (wrong TEXT)"
            )
        connection.execute("PRAGMA user_version = 2")
        connection.commit()


def _create_version_three_database(
    path: Path,
    *,
    conflicting_table: bool = False,
) -> None:
    _create_version_two_database(path)
    with open_database(path) as connection:
        connection.execute(
            "CREATE TABLE notification_reservations ("
            "product_id TEXT NOT NULL, rule_type TEXT NOT NULL, "
            "currency TEXT NOT NULL, price_amount TEXT NOT NULL, "
            "reserved_at TEXT NOT NULL, "
            "PRIMARY KEY(product_id, rule_type, currency, price_amount))"
        )
        connection.execute(
            "INSERT INTO notification_reservations VALUES (?, ?, ?, ?, ?)",
            (
                str(PRODUCT_ID.value),
                "PRICE_DROP",
                "CZK",
                "80",
                _NOW.isoformat(),
            ),
        )
        if conflicting_table:
            connection.execute(
                "CREATE TABLE daily_digest_reservations (wrong TEXT)"
            )
        connection.execute("PRAGMA user_version = 3")
        connection.commit()


def test_version_one_database_migrates_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    _create_version_one_database(path)

    entries = SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)

    assert entries[0].reference == create_reference("p1")
    assert SqliteStateStore(path).load(PRODUCT_ID) == create_snapshot()
    assert SqliteCatalogStore(path).list_refresh_batch(CATALOG_PROVIDER_ID, 1) == (
        create_reference("p1"),
    )
    with open_database(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(catalog_entries)"
            ).fetchall()
        )
        attempt = connection.execute(
            "SELECT last_refresh_attempt_at FROM catalog_entries"
        ).fetchone()
    assert version == (6,)
    assert columns == _V1_CATALOG_COLUMNS + ("last_refresh_attempt_at",)
    assert attempt == (None,)


def test_version_two_database_migrates_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    _create_version_two_database(path)

    assert SqliteStateStore(path).load(PRODUCT_ID) == create_snapshot()

    with open_database(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        reservation_columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(notification_reservations)"
            ).fetchall()
        )
        observation_count = connection.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()
    assert version == (6,)
    assert reservation_columns == (
        "product_id",
        "rule_type",
        "currency",
        "price_amount",
        "reserved_at",
    )
    assert observation_count == (1,)


def test_version_three_database_migrates_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    _create_version_three_database(path)

    assert SqliteStateStore(path).load(PRODUCT_ID) == create_snapshot()

    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        assert connection.execute(
            "SELECT product_id, rule_type, currency, price_amount, reserved_at "
            "FROM notification_reservations"
        ).fetchone() == (
            str(PRODUCT_ID.value),
            "PRICE_DROP",
            "CZK",
            "80",
            _NOW.isoformat(),
        )
        assert connection.execute(
            "PRAGMA table_info(daily_digest_reservations)"
        ).fetchall()


def test_failed_version_three_migration_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    _create_version_three_database(path, conflicting_table=True)

    with pytest.raises(CatalogStoreError) as captured:
        SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)

    assert isinstance(captured.value.__cause__, SqlitePersistenceError)
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (3,)
        columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(daily_digest_reservations)"
            ).fetchall()
        )
    assert columns == ("wrong",)


def test_failed_version_two_migration_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    _create_version_two_database(path, conflicting_table=True)

    with pytest.raises(CatalogStoreError) as captured:
        SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)

    assert isinstance(captured.value.__cause__, SqlitePersistenceError)
    with open_database(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(notification_reservations)"
            ).fetchall()
        )
    assert version == (2,)
    assert columns == ("wrong",)


def test_failed_migration_rolls_back_schema_and_version(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    _create_version_one_database(path, conflicting_index=True)

    with pytest.raises(CatalogStoreError) as captured:
        SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)

    assert isinstance(captured.value.__cause__, SqlitePersistenceError)
    with open_database(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(catalog_entries)"
            ).fetchall()
        )
    assert version == (1,)
    assert columns == _V1_CATALOG_COLUMNS


def test_future_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    with open_database(path) as connection:
        connection.execute("PRAGMA user_version = 7")
        connection.commit()

    with pytest.raises(CatalogStoreError) as captured:
        SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)

    assert isinstance(captured.value.__cause__, SqlitePersistenceError)


def test_version_five_database_migrates_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    snapshot = create_snapshot()
    SqliteStateStore(path).save(snapshot)
    with open_database(path) as connection:
        connection.execute("DROP TABLE daily_digest_baselines")
        connection.execute(
            "INSERT INTO operational_state (id, payload) VALUES (1, ?)",
            ('{"preserved":true}',),
        )
        connection.execute("PRAGMA user_version = 5")
        connection.commit()

    assert SqliteStateStore(path).load(PRODUCT_ID) == snapshot

    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        assert connection.execute(
            "SELECT payload FROM operational_state WHERE id = 1"
        ).fetchone() == ('{"preserved":true}',)
        assert connection.execute(
            "PRAGMA table_info(daily_digest_baselines)"
        ).fetchall()


def test_failed_version_five_migration_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    SqliteStateStore(path).load(PRODUCT_ID)
    with open_database(path) as connection:
        connection.execute("DROP TABLE daily_digest_baselines")
        connection.execute("CREATE TABLE daily_digest_baselines (wrong TEXT)")
        connection.execute("PRAGMA user_version = 5")
        connection.commit()

    with pytest.raises(CatalogStoreError) as captured:
        SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)

    assert isinstance(captured.value.__cause__, SqlitePersistenceError)
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (5,)
        assert tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(daily_digest_baselines)"
            ).fetchall()
        ) == ("wrong",)
