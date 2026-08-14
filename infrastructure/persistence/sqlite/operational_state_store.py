"""SQLite persistence for durable operational state."""

import json
import sqlite3
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import TypeVar

from core.operations import (
    DailyDigestDelivery,
    OperationalFailureKind,
    OperationalHealthStatus,
    OperationalNotificationKind,
    OperationalState,
    OperationalStateError,
)
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    validate_store_configuration,
)

_DOCUMENT_VERSION = 1
_EnumType = TypeVar("_EnumType", bound=Enum)


class SqliteOperationalStateStore:
    """Load and atomically replace one operational state."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Validate configuration without opening the database."""
        validated_path = validate_store_configuration(path, timeout_seconds)
        self._database = SqliteDatabase(validated_path, timeout_seconds)

    def load(self) -> OperationalState:
        """Return persisted state or the canonical initial state."""
        connection = self._open("load")
        try:
            rows = connection.execute(
                "SELECT id, payload FROM operational_state ORDER BY id"
            ).fetchall()
            if not rows:
                return OperationalState.initial()
            if len(rows) != 1 or rows[0][0] != 1 or not isinstance(rows[0][1], str):
                raise _OperationalDataError("operational state row is invalid")
            return _decode_state(rows[0][1])
        except _OperationalDataError as error:
            raise OperationalStateError(
                "invalid persisted operational state"
            ) from error
        except sqlite3.Error as error:
            raise OperationalStateError("failed to load operational state") from error
        finally:
            self._close(connection)

    def save(self, state: OperationalState) -> None:
        """Atomically replace the complete singleton state."""
        if not isinstance(state, OperationalState):
            raise TypeError("state must be an OperationalState")
        payload = _encode_state(state)
        connection = self._open("save")
        try:
            with connection:
                connection.execute(
                    "INSERT INTO operational_state (id, payload) VALUES (1, ?) "
                    "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                    (payload,),
                )
        except sqlite3.Error as error:
            raise OperationalStateError("failed to save operational state") from error
        finally:
            self._close(connection)

    def _open(self, operation: str) -> sqlite3.Connection:
        try:
            return self._database.open()
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise OperationalStateError(
                f"failed to {operation} operational state"
            ) from error

    def _close(self, connection: sqlite3.Connection) -> None:
        try:
            self._database.close(connection)
        except SqlitePersistenceError as error:
            raise OperationalStateError(
                "failed to close operational state database"
            ) from error


class _OperationalDataError(ValueError):
    """Report malformed persisted operational state data."""


def _encode_state(state: OperationalState) -> str:
    delivery = state.last_digest_delivery
    document = {
        "schema_version": _DOCUMENT_VERSION,
        "status": state.status.value,
        "failure_kind": _enum_value(state.failure_kind),
        "consecutive_failure_cycles": state.consecutive_failure_cycles,
        "incident_started_at": _timestamp_text(state.incident_started_at),
        "last_checked_at": _timestamp_text(state.last_checked_at),
        "last_recovered_at": _timestamp_text(state.last_recovered_at),
        "incident_notified": state.incident_notified,
        "pending_notification": _enum_value(state.pending_notification),
        "last_digest_delivery": (
            None
            if delivery is None
            else {
                "calendar_date": delivery.calendar_date.isoformat(),
                "delivered_at": delivery.delivered_at.isoformat(),
                "product_count": delivery.product_count,
                "promotion_included": delivery.promotion_included,
            }
        ),
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_state(payload: str) -> OperationalState:
    try:
        document = json.loads(payload)
        if not isinstance(document, dict) or set(document) != {
            "schema_version",
            "status",
            "failure_kind",
            "consecutive_failure_cycles",
            "incident_started_at",
            "last_checked_at",
            "last_recovered_at",
            "incident_notified",
            "pending_notification",
            "last_digest_delivery",
        }:
            raise _OperationalDataError("operational document shape is invalid")
        if document["schema_version"] != _DOCUMENT_VERSION:
            raise _OperationalDataError("operational document version is invalid")
        return OperationalState(
            OperationalHealthStatus(document["status"]),
            _optional_enum(document["failure_kind"], OperationalFailureKind),
            document["consecutive_failure_cycles"],
            _optional_timestamp(document["incident_started_at"]),
            _optional_timestamp(document["last_checked_at"]),
            _optional_timestamp(document["last_recovered_at"]),
            document["incident_notified"],
            _optional_enum(
                document["pending_notification"],
                OperationalNotificationKind,
            ),
            _decode_delivery(document["last_digest_delivery"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, _OperationalDataError):
            raise
        raise _OperationalDataError("operational document values are invalid") from error


def _decode_delivery(value: object) -> DailyDigestDelivery | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "calendar_date",
        "delivered_at",
        "product_count",
        "promotion_included",
    }:
        raise _OperationalDataError("digest delivery shape is invalid")
    calendar_text = value["calendar_date"]
    if not isinstance(calendar_text, str):
        raise _OperationalDataError("digest calendar date must be text")
    return DailyDigestDelivery(
        date.fromisoformat(calendar_text),
        _required_timestamp(value["delivered_at"]),
        value["product_count"],
        value["promotion_included"],
    )


def _optional_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    return _required_timestamp(value)


def _required_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise _OperationalDataError("timestamp must be text")
    return datetime.fromisoformat(value)


def _optional_enum(
    value: object,
    enum_type: type[_EnumType],
) -> _EnumType | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _OperationalDataError("enum value must be text")
    return enum_type(value)


def _enum_value(value: Enum | None) -> str | None:
    return None if value is None else str(value.value)


def _timestamp_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
