"""Schema, configuration and failure tests for SQLite persistence."""

import inspect
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

import infrastructure.persistence.sqlite as sqlite_api
from core.catalog import CatalogStoreError, ProductReference
from core.state import StateSnapshot, StateStoreError
from infrastructure.persistence.sqlite import SqliteCatalogStore, SqliteStateStore
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    _create_schema,
)
from tests.unit.persistence.helpers import PRODUCT_ID, create_snapshot
from tests.unit.persistence.sqlite_helpers import (
    CATALOG_PROVIDER_ID,
    create_reference,
    open_database,
)

_NOW = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)


def test_sqlite_public_api_is_explicit_documented_and_typed() -> None:
    assert sqlite_api.__all__ == ["SqliteCatalogStore", "SqliteStateStore"]
    assert sqlite_api.SqliteCatalogStore is SqliteCatalogStore
    assert sqlite_api.SqliteStateStore is SqliteStateStore
    for public_class in (SqliteCatalogStore, SqliteStateStore):
        assert inspect.getdoc(public_class)
        assert inspect.getdoc(public_class.__init__)
        assert inspect.signature(public_class.__init__).return_annotation is None
    assert inspect.getdoc(SqliteCatalogStore.record_discovery)
    assert inspect.getdoc(SqliteCatalogStore.list_entries)
    assert inspect.getdoc(SqliteStateStore.load)
    assert inspect.getdoc(SqliteStateStore.save)
    assert inspect.getdoc(SqliteStateStore.history)
    assert inspect.signature(SqliteCatalogStore.record_discovery).return_annotation == (
        tuple[ProductReference, ...]
    )
    assert inspect.signature(SqliteStateStore.load).return_annotation == (
        StateSnapshot | None
    )


@pytest.mark.parametrize("store_class", [SqliteCatalogStore, SqliteStateStore])
def test_constructor_rejects_invalid_path_type(store_class: type[object]) -> None:
    with pytest.raises(TypeError, match="path"):
        store_class("state.sqlite3")  # type: ignore[call-arg]


@pytest.mark.parametrize("store_class", [SqliteCatalogStore, SqliteStateStore])
@pytest.mark.parametrize("timeout", [True, 1.5, "5"])
def test_constructor_rejects_invalid_timeout_type(
    store_class: type[object],
    timeout: object,
) -> None:
    with pytest.raises(TypeError, match="timeout_seconds"):
        store_class(Path("state.sqlite3"), timeout)  # type: ignore[call-arg]


@pytest.mark.parametrize("store_class", [SqliteCatalogStore, SqliteStateStore])
@pytest.mark.parametrize("timeout", [0, -1])
def test_constructor_rejects_non_positive_timeout(
    store_class: type[object],
    timeout: int,
) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        store_class(Path("state.sqlite3"), timeout)  # type: ignore[call-arg]


def test_catalog_and_state_stores_coexist_in_one_database(tmp_path: Path) -> None:
    path = tmp_path / "price-watch.sqlite3"
    catalog = SqliteCatalogStore(path)
    state = SqliteStateStore(path)
    reference = create_reference("p1")
    snapshot = create_snapshot()

    catalog.record_discovery((reference,), _NOW)
    state.save(snapshot)

    assert SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)[0].reference == (
        reference
    )
    assert SqliteStateStore(path).load(PRODUCT_ID) == snapshot


def _create_invalid_database(path: Path, kind: str) -> None:
    with open_database(path) as connection:
        if kind == "foreign":
            connection.execute("CREATE TABLE foreign_data (value TEXT)")
        elif kind == "version":
            connection.execute("PRAGMA user_version = 2")
        elif kind == "missing":
            connection.execute("PRAGMA user_version = 1")
        elif kind == "columns":
            connection.execute(
                "CREATE TABLE catalog_entries (sequence INTEGER)"
            )
            connection.execute(
                "CREATE TABLE observations (sequence INTEGER)"
            )
            connection.execute("PRAGMA user_version = 1")
        else:
            _create_schema(connection)
            connection.execute(
                "ALTER TABLE observations ADD COLUMN unexpected TEXT"
            )
        connection.commit()


@pytest.mark.parametrize(
    "kind",
    ["foreign", "version", "missing", "columns", "observation_columns"],
)
@pytest.mark.parametrize("store_kind", ["catalog", "state"])
def test_invalid_schema_is_rejected_by_relevant_boundary(
    tmp_path: Path,
    kind: str,
    store_kind: str,
) -> None:
    path = tmp_path / f"{kind}-{store_kind}.sqlite3"
    _create_invalid_database(path, kind)

    if store_kind == "catalog":
        with pytest.raises(CatalogStoreError) as captured:
            SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)
    else:
        with pytest.raises(StateStoreError) as captured:
            SqliteStateStore(path).load(PRODUCT_ID)

    assert isinstance(captured.value.__cause__, SqlitePersistenceError)


@pytest.mark.parametrize("store_kind", ["catalog", "state"])
def test_database_connect_failure_is_wrapped_with_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    store_kind: str,
) -> None:
    failure = sqlite3.OperationalError("cannot open")

    def fail_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise failure

    monkeypatch.setattr(
        "infrastructure.persistence.sqlite.database.sqlite3.connect",
        fail_connect,
    )
    path = tmp_path / "state.sqlite3"

    if store_kind == "catalog":
        with pytest.raises(CatalogStoreError) as captured:
            SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)
    else:
        with pytest.raises(StateStoreError) as captured:
            SqliteStateStore(path).load(PRODUCT_ID)

    internal = captured.value.__cause__
    assert isinstance(internal, SqlitePersistenceError)
    assert internal.__cause__ is failure


@pytest.mark.parametrize("store_kind", ["catalog", "state"])
def test_parent_directory_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    store_kind: str,
) -> None:
    failure = OSError("mkdir failed")

    def fail_mkdir(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        raise failure

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    path = tmp_path / "missing" / "state.sqlite3"

    if store_kind == "catalog":
        with pytest.raises(CatalogStoreError) as captured:
            SqliteCatalogStore(path).record_discovery((), _NOW)
    else:
        with pytest.raises(StateStoreError) as captured:
            SqliteStateStore(path).save(create_snapshot())

    internal = captured.value.__cause__
    assert isinstance(internal, SqlitePersistenceError)
    assert internal.__cause__ is failure


@pytest.mark.parametrize("store_kind", ["catalog", "state"])
def test_connection_close_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    store_kind: str,
) -> None:
    failure = SqlitePersistenceError("close failed")

    def fail_close(
        database: SqliteDatabase,
        connection: sqlite3.Connection,
    ) -> None:
        connection.close()
        raise failure

    monkeypatch.setattr(SqliteDatabase, "close", fail_close)
    path = tmp_path / "state.sqlite3"

    if store_kind == "catalog":
        with pytest.raises(CatalogStoreError, match="close") as captured:
            SqliteCatalogStore(path).record_discovery((), _NOW)
    else:
        with pytest.raises(StateStoreError, match="close") as captured:
            SqliteStateStore(path).load(PRODUCT_ID)

    assert captured.value.__cause__ is failure
