"""SQLite persistence for weekly operational summaries."""

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from core.operations import (
    OperationalFailureCount,
    OperationalFailureKind,
    OperationalStateError,
    WeeklyOperationalSummary,
)
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    validate_store_configuration,
)

_DOCUMENT_VERSION = 1
_KEYS = {
    "version",
    "period_start",
    "failure_counts",
    "total_failed_cycles",
    "incident_count",
    "recovery_count",
    "longest_failure_streak",
    "current_failure_streak",
    "first_failure_at",
    "last_failure_at",
    "delivered_at",
}


class SqliteWeeklyOperationalSummaryStore:
    """Load and atomically replace weekly operational buckets."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Validate configuration without opening the database."""
        validated = validate_store_configuration(path, timeout_seconds)
        self._database = SqliteDatabase(validated, timeout_seconds)

    def load(self, period_start: date) -> WeeklyOperationalSummary | None:
        """Return one retained weekly bucket or None."""
        _validate_date(period_start)
        connection = self._open("load")
        try:
            row = connection.execute(
                "SELECT payload FROM weekly_operational_summaries "
                "WHERE period_start = ?",
                (period_start.isoformat(),),
            ).fetchone()
            return None if row is None else _decode(row[0])
        except (sqlite3.Error, _WeeklyDataError) as error:
            raise OperationalStateError(
                "failed to load weekly operational summary"
            ) from error
        finally:
            self._close(connection)

    def save(self, summary: WeeklyOperationalSummary) -> None:
        """Atomically retain one complete weekly bucket."""
        if not isinstance(summary, WeeklyOperationalSummary):
            raise TypeError("summary must be a WeeklyOperationalSummary")
        payload = _encode(summary)
        connection = self._open("save")
        try:
            with connection:
                connection.execute(
                    "INSERT INTO weekly_operational_summaries "
                    "(period_start, payload) VALUES (?, ?) "
                    "ON CONFLICT(period_start) DO UPDATE SET payload = excluded.payload",
                    (summary.period_start.isoformat(), payload),
                )
        except sqlite3.Error as error:
            raise OperationalStateError(
                "failed to save weekly operational summary"
            ) from error
        finally:
            self._close(connection)

    def _open(self, operation: str) -> sqlite3.Connection:
        try:
            return self._database.open()
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise OperationalStateError(
                f"failed to {operation} weekly operational summary"
            ) from error

    def _close(self, connection: sqlite3.Connection) -> None:
        try:
            self._database.close(connection)
        except SqlitePersistenceError as error:
            raise OperationalStateError(
                "failed to close weekly operational summary database"
            ) from error


class _WeeklyDataError(ValueError):
    """Report malformed weekly operational summary data."""


def _encode(summary: WeeklyOperationalSummary) -> str:
    document = {
        "version": _DOCUMENT_VERSION,
        "period_start": summary.period_start.isoformat(),
        "failure_counts": [
            {"kind": item.kind.value, "count": item.count}
            for item in summary.failure_counts
        ],
        "total_failed_cycles": summary.total_failed_cycles,
        "incident_count": summary.incident_count,
        "recovery_count": summary.recovery_count,
        "longest_failure_streak": summary.longest_failure_streak,
        "current_failure_streak": summary.current_failure_streak,
        "first_failure_at": _timestamp_text(summary.first_failure_at),
        "last_failure_at": _timestamp_text(summary.last_failure_at),
        "delivered_at": _timestamp_text(summary.delivered_at),
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def _decode(payload: object) -> WeeklyOperationalSummary:
    if not isinstance(payload, str):
        raise _WeeklyDataError("payload must be text")
    try:
        document = json.loads(payload)
        if not isinstance(document, dict) or set(document) != _KEYS:
            raise _WeeklyDataError("document keys are invalid")
        if document["version"] != _DOCUMENT_VERSION:
            raise _WeeklyDataError("document version is unsupported")
        raw_counts = document["failure_counts"]
        if not isinstance(raw_counts, list):
            raise _WeeklyDataError("failure_counts must be a list")
        counts = tuple(
            OperationalFailureCount(
                OperationalFailureKind(_required(item, "kind")),
                _required(item, "count"),
            )
            for item in raw_counts
        )
        return WeeklyOperationalSummary(
            date.fromisoformat(document["period_start"]),
            counts,
            document["total_failed_cycles"],
            document["incident_count"],
            document["recovery_count"],
            document["longest_failure_streak"],
            document["current_failure_streak"],
            _optional_timestamp(document["first_failure_at"]),
            _optional_timestamp(document["last_failure_at"]),
            _optional_timestamp(document["delivered_at"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, _WeeklyDataError):
            raise
        raise _WeeklyDataError("weekly summary document is invalid") from error


def _required(value: object, key: str) -> object:
    if not isinstance(value, dict) or set(value) != {"kind", "count"}:
        raise _WeeklyDataError("failure count is invalid")
    return value[key]


def _optional_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _WeeklyDataError("timestamp must be text or null")
    return datetime.fromisoformat(value)


def _timestamp_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _validate_date(value: object) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError("period_start must be a date")
