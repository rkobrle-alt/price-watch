"""SQLite persistence for unique logical notification reservations."""

import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from core.domain import Currency, Money, ProductId, RuleType, ValidationError
from core.notifications import (
    NotificationReservation,
    NotificationReservationError,
)
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    validate_store_configuration,
)


class SqliteNotificationReservationStore:
    """Atomically reserve logical notifications in the shared SQLite store."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Validate configuration without opening or creating the database."""
        validated_path = validate_store_configuration(path, timeout_seconds)
        self._database = SqliteDatabase(validated_path, timeout_seconds)

    def reserve(
        self,
        reservation: NotificationReservation,
        reserved_at: datetime,
    ) -> bool:
        """Persist a reservation atomically and report whether it was new."""
        _validate_reservation(reservation)
        _validate_timestamp(reserved_at)
        parameters = _identity_parameters(reservation)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._database.open()
            with connection:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO notification_reservations ("
                    "product_id, rule_type, currency, price_amount, reserved_at"
                    ") VALUES (?, ?, ?, ?, ?)",
                    (*parameters, reserved_at.isoformat()),
                )
                if cursor.rowcount == 1:
                    return True
                row = connection.execute(
                    "SELECT product_id, rule_type, currency, price_amount, "
                    "reserved_at FROM notification_reservations "
                    "WHERE product_id = ? AND rule_type = ? AND currency = ? "
                    "AND price_amount = ?",
                    parameters,
                ).fetchone()
                _decode_existing(row)
                return False
        except _ReservationDataError as error:
            raise NotificationReservationError(
                "invalid persisted notification reservation"
            ) from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise NotificationReservationError(
                "failed to reserve notification"
            ) from error
        finally:
            if connection is not None:
                _close(self._database, connection)

    def release(self, reservation: NotificationReservation) -> None:
        """Idempotently delete one reservation."""
        _validate_reservation(reservation)
        try:
            connection = self._database.open()
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise NotificationReservationError(
                "failed to release notification reservation"
            ) from error
        try:
            with connection:
                connection.execute(
                    "DELETE FROM notification_reservations "
                    "WHERE product_id = ? AND rule_type = ? AND currency = ? "
                    "AND price_amount = ?",
                    _identity_parameters(reservation),
                )
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise NotificationReservationError(
                "failed to release notification reservation"
            ) from error
        finally:
            _close(self._database, connection)


class _ReservationDataError(ValueError):
    """Report malformed persisted reservation data."""


def _validate_reservation(value: object) -> None:
    if not isinstance(value, NotificationReservation):
        raise TypeError("reservation must be a NotificationReservation")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("reserved_at must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("reserved_at must be timezone-aware")


def _identity_parameters(
    reservation: NotificationReservation,
) -> tuple[str, str, str, str]:
    return (
        str(reservation.product_id.value),
        reservation.rule_type.value,
        reservation.price.currency.value,
        _encode_amount(reservation.price.amount),
    )


def _encode_amount(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == Decimal("0"):
        return "0"
    return format(normalized, "f")


def _decode_existing(row: tuple[object, ...] | None) -> None:
    if row is None:
        raise _ReservationDataError("reserved row is missing")
    try:
        product_text, rule_text, currency_text, amount_text, timestamp_text = row
        if not all(isinstance(value, str) for value in row):
            raise _ReservationDataError("reservation values must be strings")
        product_uuid = UUID(product_text)
        if str(product_uuid) != product_text:
            raise _ReservationDataError("product_id must be canonical")
        RuleType(rule_text)
        currency = Currency(currency_text)
        amount = Decimal(amount_text)
        if _encode_amount(amount) != amount_text:
            raise _ReservationDataError("price_amount must be canonical")
        Money(amount, currency)
        ProductId(product_uuid)
        timestamp = datetime.fromisoformat(timestamp_text)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise _ReservationDataError("reserved_at must be timezone-aware")
    except (
        InvalidOperation,
        TypeError,
        ValueError,
        ValidationError,
    ) as error:
        if isinstance(error, _ReservationDataError):
            raise
        raise _ReservationDataError(
            "reservation row violates Core invariants"
        ) from error


def _close(
    database: SqliteDatabase,
    connection: sqlite3.Connection,
) -> None:
    try:
        database.close(connection)
    except SqlitePersistenceError as error:
        raise NotificationReservationError(
            "failed to close notification reservation database"
        ) from error
