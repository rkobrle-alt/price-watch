"""Tests for SQLite daily digest product membership baselines."""

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from core.domain import ProductId
from core.notifications import DailyDigestBaselineStore, DailyDigestReservationError
from infrastructure.persistence.sqlite import SqliteDailyDigestBaselineStore
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
)
from tests.unit.persistence.sqlite_helpers import open_database

_DATE = date(2026, 8, 8)
_NEXT_DATE = date(2026, 8, 9)
_LATER_DATE = date(2026, 8, 10)
_ID_ONE = ProductId(UUID("018f0000-0000-7000-8000-000000000001"))
_ID_TWO = ProductId(UUID("018f0000-0000-7000-8000-000000000002"))


def _as_contract(store: DailyDigestBaselineStore) -> DailyDigestBaselineStore:
    return store


def test_constructor_has_no_io_and_store_implements_protocol(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "catalog.sqlite3"
    store = SqliteDailyDigestBaselineStore(path)

    assert _as_contract(store) is store
    assert not path.parent.exists()


def test_stage_is_durable_canonical_replaceable_and_date_specific(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteDailyDigestBaselineStore(path)

    assert store.previous_product_ids(_DATE) is None
    store.stage(_DATE, (_ID_TWO, _ID_ONE))
    store.stage(_NEXT_DATE, ())
    assert SqliteDailyDigestBaselineStore(path).previous_product_ids(
        _NEXT_DATE
    ) == (_ID_ONE, _ID_TWO)
    assert store.previous_product_ids(_LATER_DATE) == ()

    store.stage(_NEXT_DATE, (_ID_ONE,))
    assert store.previous_product_ids(_LATER_DATE) == (_ID_ONE,)
    with open_database(path) as connection:
        payload = connection.execute(
            "SELECT product_ids FROM daily_digest_baselines "
            "WHERE calendar_date = ?",
            (_DATE.isoformat(),),
        ).fetchone()
    assert payload == (
        '{"product_ids":["018f0000-0000-7000-8000-000000000001",'
        '"018f0000-0000-7000-8000-000000000002"],"version":1}',
    )


def test_release_is_idempotent_and_removes_only_requested_date(
    tmp_path: Path,
) -> None:
    store = SqliteDailyDigestBaselineStore(tmp_path / "catalog.sqlite3")
    store.stage(_DATE, (_ID_ONE,))
    store.stage(_NEXT_DATE, (_ID_TWO,))

    store.release(_NEXT_DATE)
    store.release(_NEXT_DATE)

    assert store.previous_product_ids(_LATER_DATE) == (_ID_ONE,)


@pytest.mark.parametrize("method", ["previous_product_ids", "stage", "release"])
@pytest.mark.parametrize("value", [datetime(2026, 8, 8), "2026-08-08", object()])
def test_public_methods_reject_invalid_date_before_io(
    tmp_path: Path,
    method: str,
    value: object,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteDailyDigestBaselineStore(path)
    with pytest.raises(TypeError, match="calendar_date"):
        if method == "stage":
            store.stage(value, ())  # type: ignore[arg-type]
        else:
            getattr(store, method)(value)
    assert not path.exists()


@pytest.mark.parametrize(
    ("value", "error"),
    [([], TypeError), ((object(),), TypeError), ((_ID_ONE, _ID_ONE), ValueError)],
)
def test_stage_rejects_invalid_product_ids_before_io(
    tmp_path: Path,
    value: object,
    error: type[Exception],
) -> None:
    path = tmp_path / "catalog.sqlite3"
    with pytest.raises(error, match="product_ids"):
        SqliteDailyDigestBaselineStore(path).stage(  # type: ignore[arg-type]
            _DATE,
            value,
        )
    assert not path.exists()


@pytest.mark.parametrize(
    "payload",
    [
        sqlite3.Binary(b"not text"),
        "not json",
        "[]",
        '{"version":1}',
        '{"product_ids":[],"unexpected":1,"version":1}',
        '{"product_ids":[],"version":true}',
        '{"product_ids":[],"version":2}',
        '{"product_ids":{},"version":1}',
        '{"product_ids":[1],"version":1}',
        '{"product_ids":["invalid"],"version":1}',
        (
            '{"product_ids":["018f0000-0000-7000-8000-000000000001",'
            '"018f0000-0000-7000-8000-000000000001"],"version":1}'
        ),
        (
            '{"product_ids":["018f0000-0000-7000-8000-000000000002",'
            '"018f0000-0000-7000-8000-000000000001"],"version":1}'
        ),
        '{"version":1,"product_ids":[]}',
    ],
)
def test_malformed_persisted_document_is_rejected(
    tmp_path: Path,
    payload: object,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteDailyDigestBaselineStore(path)
    store.stage(_DATE, ())
    with open_database(path) as connection:
        connection.execute(
            "UPDATE daily_digest_baselines SET product_ids = ?",
            (payload,),
        )
        connection.commit()

    with pytest.raises(DailyDigestReservationError, match="invalid persisted"):
        store.previous_product_ids(_NEXT_DATE)


@pytest.mark.parametrize("method", ["previous_product_ids", "stage", "release"])
def test_database_open_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    failure = SqlitePersistenceError("open failed")
    monkeypatch.setattr(
        SqliteDatabase,
        "open",
        lambda database: (_ for _ in ()).throw(failure),
    )
    store = SqliteDailyDigestBaselineStore(tmp_path / "catalog.sqlite3")

    with pytest.raises(DailyDigestReservationError) as captured:
        if method == "stage":
            store.stage(_DATE, ())
        else:
            getattr(store, method)(_DATE)
    assert captured.value.__cause__ is failure


@pytest.mark.parametrize("method", ["previous_product_ids", "stage", "release"])
def test_sqlite_operation_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    failure = sqlite3.OperationalError("query failed")

    class _FailingConnection:
        def __enter__(self) -> "_FailingConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, *args: object) -> object:
            raise failure

    connection = cast(sqlite3.Connection, _FailingConnection())
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: connection)
    monkeypatch.setattr(SqliteDatabase, "close", lambda database, value: None)
    store = SqliteDailyDigestBaselineStore(tmp_path / "catalog.sqlite3")

    with pytest.raises(DailyDigestReservationError) as captured:
        if method == "stage":
            store.stage(_DATE, ())
        else:
            getattr(store, method)(_DATE)
    assert captured.value.__cause__ is failure


def test_close_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    SqliteDailyDigestBaselineStore(path).stage(_DATE, ())
    failure = SqlitePersistenceError("close failed")

    def fail_close(database: SqliteDatabase, connection: sqlite3.Connection) -> None:
        connection.close()
        raise failure

    monkeypatch.setattr(SqliteDatabase, "close", fail_close)
    with pytest.raises(DailyDigestReservationError, match="close") as captured:
        SqliteDailyDigestBaselineStore(path).previous_product_ids(_NEXT_DATE)
    assert captured.value.__cause__ is failure


def test_persisted_json_shape_is_strictly_versioned(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    SqliteDailyDigestBaselineStore(path).stage(_DATE, (_ID_ONE,))
    with open_database(path) as connection:
        value = connection.execute(
            "SELECT product_ids FROM daily_digest_baselines"
        ).fetchone()[0]

    assert json.loads(value) == {
        "product_ids": [str(_ID_ONE.value)],
        "version": 1,
    }
