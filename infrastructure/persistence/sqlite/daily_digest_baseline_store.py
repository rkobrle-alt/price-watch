"""SQLite persistence for daily digest product membership baselines."""

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from core.domain import ProductId
from core.notifications import DailyDigestReservationError
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    validate_store_configuration,
)

_DOCUMENT_VERSION = 1


class SqliteDailyDigestBaselineStore:
    """Persist versioned daily digest memberships in the shared database."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Validate configuration without opening the database."""
        validated_path = validate_store_configuration(path, timeout_seconds)
        self._database = SqliteDatabase(validated_path, timeout_seconds)

    def previous_product_ids(
        self,
        calendar_date: date,
    ) -> tuple[ProductId, ...] | None:
        """Return the latest valid baseline strictly before a digest date."""
        _validate_date(calendar_date)
        connection = self._open("load daily digest baseline")
        try:
            row = connection.execute(
                "SELECT product_ids FROM daily_digest_baselines "
                "WHERE calendar_date < ? ORDER BY calendar_date DESC LIMIT 1",
                (calendar_date.isoformat(),),
            ).fetchone()
            return None if row is None else _decode_product_ids(row[0])
        except _BaselineDataError as error:
            raise DailyDigestReservationError(
                "invalid persisted daily digest baseline"
            ) from error
        except sqlite3.Error as error:
            raise DailyDigestReservationError(
                "failed to load daily digest baseline"
            ) from error
        finally:
            self._close(connection)

    def stage(
        self,
        calendar_date: date,
        product_ids: tuple[ProductId, ...],
    ) -> None:
        """Insert or replace the canonical membership for one digest date."""
        _validate_date(calendar_date)
        _validate_product_ids(product_ids)
        payload = _encode_product_ids(product_ids)
        connection = self._open("stage daily digest baseline")
        try:
            with connection:
                connection.execute(
                    "INSERT INTO daily_digest_baselines "
                    "(calendar_date, product_ids) VALUES (?, ?) "
                    "ON CONFLICT(calendar_date) DO UPDATE SET "
                    "product_ids = excluded.product_ids",
                    (calendar_date.isoformat(), payload),
                )
        except sqlite3.Error as error:
            raise DailyDigestReservationError(
                "failed to stage daily digest baseline"
            ) from error
        finally:
            self._close(connection)

    def release(self, calendar_date: date) -> None:
        """Idempotently delete the baseline for one digest date."""
        _validate_date(calendar_date)
        connection = self._open("release daily digest baseline")
        try:
            with connection:
                connection.execute(
                    "DELETE FROM daily_digest_baselines WHERE calendar_date = ?",
                    (calendar_date.isoformat(),),
                )
        except sqlite3.Error as error:
            raise DailyDigestReservationError(
                "failed to release daily digest baseline"
            ) from error
        finally:
            self._close(connection)

    def _open(self, operation: str) -> sqlite3.Connection:
        try:
            return self._database.open()
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise DailyDigestReservationError(f"failed to {operation}") from error

    def _close(self, connection: sqlite3.Connection) -> None:
        try:
            self._database.close(connection)
        except SqlitePersistenceError as error:
            raise DailyDigestReservationError(
                "failed to close daily digest baseline database"
            ) from error


class _BaselineDataError(ValueError):
    """Report malformed persisted baseline documents."""


def _validate_date(value: object) -> None:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError("calendar_date must be a date")


def _validate_product_ids(value: object) -> None:
    if not isinstance(value, tuple):
        raise TypeError("product_ids must be a tuple")
    if not all(isinstance(identifier, ProductId) for identifier in value):
        raise TypeError("product_ids must contain ProductId values")
    if len(set(value)) != len(value):
        raise ValueError("product_ids must contain unique identifiers")


def _encode_product_ids(product_ids: tuple[ProductId, ...]) -> str:
    document = {
        "product_ids": sorted(str(identifier.value) for identifier in product_ids),
        "version": _DOCUMENT_VERSION,
    }
    return json.dumps(document, separators=(",", ":"), sort_keys=True)


def _decode_product_ids(value: object) -> tuple[ProductId, ...]:
    if not isinstance(value, str):
        raise _BaselineDataError("baseline document must be a string")
    try:
        document = json.loads(value)
    except (json.JSONDecodeError, TypeError) as error:
        raise _BaselineDataError("baseline document must be JSON") from error
    if not isinstance(document, dict) or set(document) != {"product_ids", "version"}:
        raise _BaselineDataError("baseline document has invalid fields")
    if (
        not isinstance(document["version"], int)
        or isinstance(document["version"], bool)
        or document["version"] != _DOCUMENT_VERSION
    ):
        raise _BaselineDataError("baseline document version is unsupported")
    identifiers = document["product_ids"]
    if not isinstance(identifiers, list) or not all(
        isinstance(identifier, str) for identifier in identifiers
    ):
        raise _BaselineDataError("baseline product identifiers are invalid")
    try:
        decoded = tuple(ProductId(UUID(identifier)) for identifier in identifiers)
    except (ValueError, TypeError) as error:
        raise _BaselineDataError("baseline product identifiers are invalid") from error
    if len(set(decoded)) != len(decoded):
        raise _BaselineDataError("baseline product identifiers must be unique")
    if value != _encode_product_ids(decoded):
        raise _BaselineDataError("baseline document must be canonical")
    return decoded
