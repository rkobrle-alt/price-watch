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
    assert version == (2,)
    assert columns == _V1_CATALOG_COLUMNS + ("last_refresh_attempt_at",)
    assert attempt == (None,)


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
        connection.execute("PRAGMA user_version = 3")
        connection.commit()

    with pytest.raises(CatalogStoreError) as captured:
        SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)

    assert isinstance(captured.value.__cause__, SqlitePersistenceError)
