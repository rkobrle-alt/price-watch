"""SQLite persistence for daily digest calendar reservations."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

from core.notifications import DailyDigestReservationError
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    validate_store_configuration,
)


class SqliteDailyDigestReservationStore:
    """Atomically reserve local calendar dates in the shared database."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Validate configuration without opening the database."""
        validated_path = validate_store_configuration(path, timeout_seconds)
        self._database = SqliteDatabase(validated_path, timeout_seconds)

    def reserve(self, calendar_date: date, reserved_at: datetime) -> bool:
        """Persist a date atomically and report whether it was new."""
        _validate_date(calendar_date)
        _validate_timestamp(reserved_at)
        try:
            connection = self._database.open()
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise DailyDigestReservationError(
                "failed to reserve daily digest"
            ) from error
        try:
            with connection:
                _validate_persisted_rows(connection)
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO daily_digest_reservations "
                    "(calendar_date, reserved_at) VALUES (?, ?)",
                    (calendar_date.isoformat(), reserved_at.isoformat()),
                )
                return cursor.rowcount == 1
        except _DigestDataError as error:
            raise DailyDigestReservationError(
                "invalid persisted daily digest reservation"
            ) from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise DailyDigestReservationError(
                "failed to reserve daily digest"
            ) from error
        finally:
            _close(self._database, connection)

    def release(self, calendar_date: date) -> None:
        """Idempotently delete a calendar-date reservation."""
        _validate_date(calendar_date)
        try:
            connection = self._database.open()
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise DailyDigestReservationError(
                "failed to release daily digest reservation"
            ) from error
        try:
            with connection:
                _validate_persisted_rows(connection)
                connection.execute(
                    "DELETE FROM daily_digest_reservations "
                    "WHERE calendar_date = ?",
                    (calendar_date.isoformat(),),
                )
        except _DigestDataError as error:
            raise DailyDigestReservationError(
                "invalid persisted daily digest reservation"
            ) from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise DailyDigestReservationError(
                "failed to release daily digest reservation"
            ) from error
        finally:
            _close(self._database, connection)


class _DigestDataError(ValueError):
    """Report malformed persisted digest reservation values."""


def _validate_date(value: object) -> None:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError("calendar_date must be a date")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("reserved_at must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("reserved_at must be timezone-aware")


def _validate_persisted_rows(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT calendar_date, reserved_at FROM daily_digest_reservations"
    ).fetchall()
    for calendar_text, timestamp_text in rows:
        if not isinstance(calendar_text, str) or not isinstance(timestamp_text, str):
            raise _DigestDataError("digest reservation values must be strings")
        try:
            parsed_date = date.fromisoformat(calendar_text)
            parsed_timestamp = datetime.fromisoformat(timestamp_text)
        except ValueError as error:
            raise _DigestDataError("digest reservation values are invalid") from error
        if parsed_date.isoformat() != calendar_text:
            raise _DigestDataError("calendar_date must be canonical")
        if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
            raise _DigestDataError("reserved_at must be timezone-aware")
        if parsed_timestamp.isoformat() != timestamp_text:
            raise _DigestDataError("reserved_at must be canonical")


def _close(database: SqliteDatabase, connection: sqlite3.Connection) -> None:
    try:
        database.close(connection)
    except SqlitePersistenceError as error:
        raise DailyDigestReservationError(
            "failed to close daily digest reservation database"
        ) from error
