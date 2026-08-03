"""Behavior tests for durable SQLite catalog refresh ordering."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

from core.catalog import CatalogRefreshStore, CatalogStoreError, ProductReference
from core.domain import ProviderId
from infrastructure.persistence.sqlite import SqliteCatalogStore
from infrastructure.persistence.sqlite.database import SqliteDatabase
from tests.unit.persistence.sqlite_helpers import (
    CATALOG_PROVIDER_ID,
    OTHER_PROVIDER_ID,
    create_reference,
    open_database,
)

_NOW = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)


def _as_refresh_store(store: CatalogRefreshStore) -> CatalogRefreshStore:
    return store


def test_store_structurally_implements_refresh_contract(tmp_path: Path) -> None:
    store = SqliteCatalogStore(tmp_path / "catalog.sqlite3")

    assert _as_refresh_store(store) is store


@pytest.mark.parametrize("provider_id", [object(), "provider"])
def test_list_refresh_batch_rejects_invalid_provider_type(
    tmp_path: Path,
    provider_id: object,
) -> None:
    with pytest.raises(TypeError, match="provider_id"):
        SqliteCatalogStore(tmp_path / "catalog.sqlite3").list_refresh_batch(
            cast(ProviderId, provider_id),
            1,
        )


@pytest.mark.parametrize("limit", [True, 1.5, "1"])
def test_list_refresh_batch_rejects_invalid_limit_type(
    tmp_path: Path,
    limit: object,
) -> None:
    with pytest.raises(TypeError, match="limit"):
        SqliteCatalogStore(tmp_path / "catalog.sqlite3").list_refresh_batch(
            CATALOG_PROVIDER_ID,
            cast(int, limit),
        )


@pytest.mark.parametrize("limit", [0, -1])
def test_list_refresh_batch_rejects_non_positive_limit(
    tmp_path: Path,
    limit: int,
) -> None:
    with pytest.raises(ValueError, match="limit"):
        SqliteCatalogStore(tmp_path / "catalog.sqlite3").list_refresh_batch(
            CATALOG_PROVIDER_ID,
            limit,
        )


@pytest.mark.parametrize("references", [[], (object(),)])
def test_record_attempt_rejects_invalid_reference_collection(
    tmp_path: Path,
    references: object,
) -> None:
    with pytest.raises(TypeError, match="references"):
        SqliteCatalogStore(tmp_path / "catalog.sqlite3").record_refresh_attempt(
            cast(tuple[ProductReference, ...], references),
            _NOW,
        )


def test_record_attempt_rejects_duplicate_identities(tmp_path: Path) -> None:
    reference = create_reference("p1")

    with pytest.raises(ValueError, match="unique"):
        SqliteCatalogStore(tmp_path / "catalog.sqlite3").record_refresh_attempt(
            (reference, reference),
            _NOW,
        )


@pytest.mark.parametrize(
    ("timestamp", "exception_type"),
    [("now", TypeError), (datetime(2026, 8, 4, 10, 0), ValueError)],
)
def test_record_attempt_rejects_invalid_timestamp(
    tmp_path: Path,
    timestamp: object,
    exception_type: type[Exception],
) -> None:
    with pytest.raises(exception_type, match="attempted_at"):
        SqliteCatalogStore(tmp_path / "catalog.sqlite3").record_refresh_attempt(
            (),
            cast(datetime, timestamp),
        )


def test_empty_attempt_is_valid_and_initializes_schema(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"

    SqliteCatalogStore(path).record_refresh_attempt((), _NOW)

    assert path.is_file()
    assert SqliteCatalogStore(path).list_refresh_batch(CATALOG_PROVIDER_ID, 5) == ()


def test_refresh_batch_prioritizes_never_attempted_then_oldest_attempt(
    tmp_path: Path,
) -> None:
    store = SqliteCatalogStore(tmp_path / "catalog.sqlite3")
    first = create_reference("p1")
    second = create_reference("p2")
    third = create_reference("p3")
    other = create_reference("p4", provider_id=OTHER_PROVIDER_ID)
    store.record_discovery((first, second, third, other), _NOW)

    assert store.list_refresh_batch(CATALOG_PROVIDER_ID, 2) == (first, second)
    store.record_refresh_attempt((first,), _NOW + timedelta(minutes=1))
    assert store.list_refresh_batch(CATALOG_PROVIDER_ID, 3) == (
        second,
        third,
        first,
    )
    store.record_refresh_attempt((second,), _NOW + timedelta(minutes=3))
    store.record_refresh_attempt((third,), _NOW + timedelta(minutes=2))

    assert store.list_refresh_batch(CATALOG_PROVIDER_ID, 3) == (
        first,
        third,
        second,
    )
    assert store.list_refresh_batch(OTHER_PROVIDER_ID, 5) == (other,)


def test_equal_attempt_times_use_catalog_insertion_order(tmp_path: Path) -> None:
    store = SqliteCatalogStore(tmp_path / "catalog.sqlite3")
    references = tuple(create_reference(f"p{index}") for index in range(3))
    store.record_discovery(references, _NOW)
    store.record_refresh_attempt(references, _NOW)

    assert store.list_refresh_batch(CATALOG_PROVIDER_ID, 3) == references


def test_unknown_attempt_identity_rolls_back_complete_batch(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    retained = create_reference("p1")
    unknown = create_reference("p2")
    store.record_discovery((retained,), _NOW)

    with pytest.raises(ValueError, match="exist"):
        store.record_refresh_attempt((retained, unknown), _NOW)

    with open_database(path) as connection:
        value = connection.execute(
            "SELECT last_refresh_attempt_at FROM catalog_entries"
        ).fetchone()
    assert value == (None,)


def test_stale_attempt_rolls_back_complete_batch(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    references = (create_reference("p1"), create_reference("p2"))
    store.record_discovery(references, _NOW)
    latest = _NOW + timedelta(hours=2)
    store.record_refresh_attempt(references, latest)

    with pytest.raises(ValueError, match="cannot precede"):
        store.record_refresh_attempt(references, latest - timedelta(seconds=1))

    with open_database(path) as connection:
        values = connection.execute(
            "SELECT last_refresh_attempt_at FROM catalog_entries ORDER BY sequence"
        ).fetchall()
    assert values == [(latest.isoformat(),), (latest.isoformat(),)]


@pytest.mark.parametrize("value", [1, "invalid", "2026-08-04T10:00:00"])
def test_invalid_persisted_attempt_is_wrapped(
    tmp_path: Path,
    value: object,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    store.record_discovery((create_reference("p1"),), _NOW)
    with open_database(path) as connection:
        connection.execute(
            "UPDATE catalog_entries SET last_refresh_attempt_at = ?",
            (value,),
        )
        connection.commit()

    with pytest.raises(CatalogStoreError, match="invalid persisted") as captured:
        store.list_refresh_batch(CATALOG_PROVIDER_ID, 1)

    assert captured.value.__cause__ is not None

def test_later_attempt_advances_existing_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    reference = create_reference("p1")
    store.record_discovery((reference,), _NOW)
    store.record_refresh_attempt((reference,), _NOW)
    later = _NOW + timedelta(minutes=1)

    store.record_refresh_attempt((reference,), later)

    with open_database(path) as connection:
        value = connection.execute(
            "SELECT last_refresh_attempt_at FROM catalog_entries"
        ).fetchone()
    assert value == (later.isoformat(),)


def test_record_wraps_invalid_persisted_previous_attempt(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    reference = create_reference("p1")
    store.record_discovery((reference,), _NOW)
    with open_database(path) as connection:
        connection.execute(
            "UPDATE catalog_entries SET last_refresh_attempt_at = 'invalid'"
        )
        connection.commit()

    with pytest.raises(CatalogStoreError, match="invalid persisted") as captured:
        store.record_refresh_attempt((reference,), _NOW)

    assert captured.value.__cause__ is not None


def test_list_wraps_invalid_persisted_reference(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    store.record_discovery((create_reference("p1"),), _NOW)
    with open_database(path) as connection:
        connection.execute("UPDATE catalog_entries SET url = ''")
        connection.commit()

    with pytest.raises(CatalogStoreError, match="invalid persisted") as captured:
        store.list_refresh_batch(CATALOG_PROVIDER_ID, 1)

    assert captured.value.__cause__ is not None


@pytest.mark.parametrize("operation", ["list", "record"])
def test_refresh_operations_wrap_database_open_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    failure = sqlite3.OperationalError("cannot open")

    def fail_open(database: SqliteDatabase) -> sqlite3.Connection:
        raise failure

    monkeypatch.setattr(SqliteDatabase, "open", fail_open)
    store = SqliteCatalogStore(tmp_path / "catalog.sqlite3")

    with pytest.raises(CatalogStoreError) as captured:
        if operation == "list":
            store.list_refresh_batch(CATALOG_PROVIDER_ID, 1)
        else:
            store.record_refresh_attempt((), _NOW)

    assert captured.value.__cause__ is failure

def test_record_wraps_transaction_query_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = sqlite3.OperationalError("query failed")

    class FailingConnection:
        def __enter__(self) -> "FailingConnection":
            return self

        def __exit__(
            self,
            exception_type: type[BaseException] | None,
            exception: BaseException | None,
            traceback: object | None,
        ) -> None:
            return None

        def execute(
            self,
            statement: str,
            parameters: tuple[str, str],
        ) -> None:
            raise failure

    connection = FailingConnection()
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: connection)
    monkeypatch.setattr(SqliteDatabase, "close", lambda database, value: None)

    with pytest.raises(CatalogStoreError) as captured:
        SqliteCatalogStore(tmp_path / "catalog.sqlite3").record_refresh_attempt(
            (create_reference("p1"),),
            _NOW,
        )

    assert captured.value.__cause__ is failure