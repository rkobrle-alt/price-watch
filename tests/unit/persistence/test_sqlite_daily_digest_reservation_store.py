"""Tests for SQLite daily digest calendar reservations."""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.notifications import (
    DailyDigestReservationError,
    DailyDigestReservationStore,
)
from infrastructure.persistence.sqlite import SqliteDailyDigestReservationStore
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
)
from tests.unit.persistence.sqlite_helpers import open_database

_DATE = date(2026, 8, 8)
_NEXT_DATE = date(2026, 8, 9)
_NOW = datetime(2026, 8, 8, 6, 0, tzinfo=UTC)


def _as_contract(
    store: DailyDigestReservationStore,
) -> DailyDigestReservationStore:
    return store


def test_constructor_has_no_io_and_store_implements_protocol(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "catalog.sqlite3"
    store = SqliteDailyDigestReservationStore(path)

    assert _as_contract(store) is store
    assert not path.parent.exists()


def test_reservation_is_atomic_durable_and_date_specific(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"

    assert SqliteDailyDigestReservationStore(path).reserve(_DATE, _NOW)
    assert not SqliteDailyDigestReservationStore(path).reserve(_DATE, _NOW)
    assert SqliteDailyDigestReservationStore(path).reserve(_NEXT_DATE, _NOW)


def test_release_is_idempotent_and_permits_retry(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteDailyDigestReservationStore(path)
    assert store.reserve(_DATE, _NOW)

    store.release(_DATE)
    store.release(_DATE)

    assert store.reserve(_DATE, _NOW)


@pytest.mark.parametrize("value", [_NOW, "2026-08-08", object()])
@pytest.mark.parametrize("method", ["reserve", "release"])
def test_public_methods_reject_invalid_date_before_io(
    tmp_path: Path,
    value: object,
    method: str,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteDailyDigestReservationStore(path)
    with pytest.raises(TypeError, match="calendar_date"):
        if method == "reserve":
            store.reserve(value, _NOW)  # type: ignore[arg-type]
        else:
            store.release(value)  # type: ignore[arg-type]
    assert not path.exists()


@pytest.mark.parametrize(
    ("value", "error"),
    [("now", TypeError), (datetime(2026, 8, 8), ValueError)],
)
def test_reserve_rejects_invalid_timestamp_before_io(
    tmp_path: Path,
    value: object,
    error: type[Exception],
) -> None:
    path = tmp_path / "catalog.sqlite3"
    with pytest.raises(error, match="reserved_at"):
        SqliteDailyDigestReservationStore(path).reserve(  # type: ignore[arg-type]
            _DATE,
            value,
        )
    assert not path.exists()


@pytest.mark.parametrize(
    ("calendar_text", "timestamp_text"),
    [
        (1, _NOW.isoformat()),
        (sqlite3.Binary(b"date"), _NOW.isoformat()),
        (_DATE.isoformat(), sqlite3.Binary(b"timestamp")),
        ("invalid", _NOW.isoformat()),
        ("20260808", _NOW.isoformat()),
        (_DATE.isoformat(), "invalid"),
        (_DATE.isoformat(), datetime(2026, 8, 8).isoformat()),
        (_DATE.isoformat(), "20260808T060000+0000"),
    ],
)
def test_malformed_persisted_rows_are_rejected(
    tmp_path: Path,
    calendar_text: object,
    timestamp_text: object,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteDailyDigestReservationStore(path)
    assert store.reserve(_NEXT_DATE, _NOW)
    with open_database(path) as connection:
        connection.execute("DELETE FROM daily_digest_reservations")
        connection.execute(
            "INSERT INTO daily_digest_reservations "
            "(calendar_date, reserved_at) VALUES (?, ?)",
            (calendar_text, timestamp_text),
        )
        connection.commit()

    with pytest.raises(DailyDigestReservationError, match="invalid persisted"):
        store.reserve(_DATE, _NOW)
    with pytest.raises(DailyDigestReservationError, match="invalid persisted"):
        store.release(_DATE)


@pytest.mark.parametrize("method", ["reserve", "release"])
def test_database_open_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    failure = SqlitePersistenceError("open failed")
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: (_ for _ in ()).throw(failure))
    store = SqliteDailyDigestReservationStore(tmp_path / "catalog.sqlite3")

    with pytest.raises(DailyDigestReservationError) as captured:
        if method == "reserve":
            store.reserve(_DATE, _NOW)
        else:
            store.release(_DATE)
    assert captured.value.__cause__ is failure


@pytest.mark.parametrize("method", ["reserve", "release"])
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

    connection = cast_connection(_FailingConnection())
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: connection)
    monkeypatch.setattr(SqliteDatabase, "close", lambda database, value: None)
    store = SqliteDailyDigestReservationStore(tmp_path / "catalog.sqlite3")

    with pytest.raises(DailyDigestReservationError) as captured:
        if method == "reserve":
            store.reserve(_DATE, _NOW)
        else:
            store.release(_DATE)
    assert captured.value.__cause__ is failure


def test_close_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    SqliteDailyDigestReservationStore(path).reserve(_DATE, _NOW)
    failure = SqlitePersistenceError("close failed")

    def fail_close(database: SqliteDatabase, connection: sqlite3.Connection) -> None:
        connection.close()
        raise failure

    monkeypatch.setattr(SqliteDatabase, "close", fail_close)
    with pytest.raises(DailyDigestReservationError, match="close") as captured:
        SqliteDailyDigestReservationStore(path).reserve(_NEXT_DATE, _NOW)
    assert captured.value.__cause__ is failure


def cast_connection(value: object) -> sqlite3.Connection:
    """Keep deliberate fake-connection typing local to failure tests."""
    return value  # type: ignore[return-value]
