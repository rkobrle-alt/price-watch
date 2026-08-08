"""Tests for durable SQLite notification reservations."""

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from core.domain import Currency, Money, ProductId, RuleType
from core.notifications import (
    NotificationReservation,
    NotificationReservationError,
    NotificationReservationStore,
)
from infrastructure.persistence.sqlite import SqliteNotificationReservationStore
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
)
from tests.unit.persistence.sqlite_helpers import open_database

_NOW = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)


def _reservation(amount: str = "80.00") -> NotificationReservation:
    return NotificationReservation(
        ProductId(UUID("30000000-0000-4000-8000-000000000001")),
        RuleType.PRICE_DROP,
        Money(Decimal(amount), Currency.CZK),
    )


def _as_contract(store: NotificationReservationStore) -> object:
    return store


def test_store_structurally_implements_contract(tmp_path: Path) -> None:
    store = SqliteNotificationReservationStore(tmp_path / "catalog.sqlite3")

    assert _as_contract(store) is store


@pytest.mark.parametrize(
    ("arguments", "exception"),
    [
        (("catalog.sqlite3",), TypeError),
        ((Path("catalog.sqlite3"), True), TypeError),
        ((Path("catalog.sqlite3"), 0), ValueError),
    ],
)
def test_constructor_validates_arguments(
    arguments: tuple[object, ...],
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        SqliteNotificationReservationStore(*arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("reservation", [object(), "reservation"])
def test_public_operations_reject_invalid_reservation(
    tmp_path: Path,
    reservation: object,
) -> None:
    store = SqliteNotificationReservationStore(tmp_path / "catalog.sqlite3")

    with pytest.raises(TypeError, match="reservation"):
        store.reserve(cast(NotificationReservation, reservation), _NOW)
    with pytest.raises(TypeError, match="reservation"):
        store.release(cast(NotificationReservation, reservation))


@pytest.mark.parametrize(
    ("timestamp", "exception"),
    [("now", TypeError), (datetime(2026, 8, 8, 8, 0), ValueError)],
)
def test_reserve_rejects_invalid_timestamp(
    tmp_path: Path,
    timestamp: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception, match="reserved_at"):
        SqliteNotificationReservationStore(
            tmp_path / "catalog.sqlite3"
        ).reserve(_reservation(), cast(datetime, timestamp))


def test_equal_decimal_prices_share_one_durable_reservation(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    first = SqliteNotificationReservationStore(path)

    assert first.reserve(_reservation("80.00"), _NOW) is True
    assert SqliteNotificationReservationStore(path).reserve(
        _reservation("80.0"),
        _NOW,
    ) is False
    assert SqliteNotificationReservationStore(path).reserve(
        _reservation("79"),
        _NOW,
    ) is True
    assert SqliteNotificationReservationStore(path).reserve(
        _reservation("0.00"),
        _NOW,
    ) is True
    with open_database(path) as connection:
        rows = connection.execute(
            "SELECT price_amount FROM notification_reservations "
            "ORDER BY price_amount"
        ).fetchall()
    assert rows == [("0",), ("79",), ("80",)]


def test_release_is_idempotent_and_allows_retry(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteNotificationReservationStore(path)
    reservation = _reservation()
    assert store.reserve(reservation, _NOW)

    store.release(reservation)
    store.release(reservation)

    assert store.reserve(reservation, _NOW) is True


@pytest.mark.parametrize("operation", ["reserve", "release"])
def test_operations_wrap_open_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    failure = SqlitePersistenceError("open failed")
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: (_ for _ in ()).throw(failure))
    store = SqliteNotificationReservationStore(tmp_path / "catalog.sqlite3")

    with pytest.raises(NotificationReservationError) as captured:
        if operation == "reserve":
            store.reserve(_reservation(), _NOW)
        else:
            store.release(_reservation())

    assert captured.value.__cause__ is failure


@pytest.mark.parametrize("operation", ["reserve", "release"])
def test_operations_wrap_query_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    failure = sqlite3.OperationalError("query failed")

    class _Connection:
        def __enter__(self) -> "_Connection":
            return self

        def __exit__(self, *arguments: object) -> None:
            return None

        def execute(self, *arguments: object) -> object:
            raise failure

    connection = _Connection()
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: connection)
    monkeypatch.setattr(SqliteDatabase, "close", lambda database, value: None)
    store = SqliteNotificationReservationStore(tmp_path / "catalog.sqlite3")

    with pytest.raises(NotificationReservationError) as captured:
        if operation == "reserve":
            store.reserve(_reservation(), _NOW)
        else:
            store.release(_reservation())

    assert captured.value.__cause__ is failure


def test_close_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = SqlitePersistenceError("close failed")

    def fail_close(
        database: SqliteDatabase,
        connection: sqlite3.Connection,
    ) -> None:
        connection.close()
        raise failure

    monkeypatch.setattr(
        SqliteDatabase,
        "close",
        fail_close,
    )

    with pytest.raises(NotificationReservationError, match="close") as captured:
        SqliteNotificationReservationStore(
            tmp_path / "catalog.sqlite3"
        ).reserve(_reservation(), _NOW)

    assert captured.value.__cause__ is failure


class _Cursor:
    rowcount = 0


class _ConflictConnection:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row
        self._calls = 0

    def __enter__(self) -> "_ConflictConnection":
        return self

    def __exit__(self, *arguments: object) -> None:
        return None

    def execute(self, *arguments: object) -> object:
        self._calls += 1
        if self._calls == 1:
            return _Cursor()
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


@pytest.mark.parametrize(
    "row",
    [
        None,
        (1, "PRICE_DROP", "CZK", "80", _NOW.isoformat()),
        ("bad", "PRICE_DROP", "CZK", "80", _NOW.isoformat()),
        ("AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", "PRICE_DROP", "CZK", "80", _NOW.isoformat()),
        ("30000000-0000-4000-8000-000000000001", "BAD", "CZK", "80", _NOW.isoformat()),
        ("30000000-0000-4000-8000-000000000001", "PRICE_DROP", "BAD", "80", _NOW.isoformat()),
        ("30000000-0000-4000-8000-000000000001", "PRICE_DROP", "CZK", "bad", _NOW.isoformat()),
        ("30000000-0000-4000-8000-000000000001", "PRICE_DROP", "CZK", "80.00", _NOW.isoformat()),
        ("30000000-0000-4000-8000-000000000001", "PRICE_DROP", "CZK", "-1", _NOW.isoformat()),
        ("30000000-0000-4000-8000-000000000001", "PRICE_DROP", "CZK", "80", "bad"),
        ("30000000-0000-4000-8000-000000000001", "PRICE_DROP", "CZK", "80", "2026-08-08T08:00:00"),
    ],
)
def test_invalid_persisted_conflict_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    row: tuple[object, ...] | None,
) -> None:
    connection = _ConflictConnection(row)
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: connection)
    monkeypatch.setattr(SqliteDatabase, "close", lambda database, value: None)

    with pytest.raises(NotificationReservationError, match="invalid persisted"):
        SqliteNotificationReservationStore(
            tmp_path / "catalog.sqlite3"
        ).reserve(_reservation(), _NOW)
