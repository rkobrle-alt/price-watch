"""Transactional delivery evidence for one serialized Supervisor App writer."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from core.notifications import DailyDigestReservationError, DigestDeliveryPhase as Phase, DigestDeliveryRecord
from infrastructure.persistence.sqlite.database import SqliteDatabase, SqlitePersistenceError, validate_store_configuration


class SqliteDigestDeliveryStore:
    """Persist preparation and handoff separately from mailbox delivery."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Configure the shared database without opening or recovering it."""
        self._database = SqliteDatabase(validate_store_configuration(path, timeout_seconds), timeout_seconds)

    def recover(self, timestamp: datetime) -> None:
        """Recover abandoned preparation once at serialized App startup."""
        _timestamp(timestamp)
        with self._session() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute("SELECT * FROM digest_delivery_attempts WHERE phase IN ('preparing', 'sending')").fetchall()
            for row in pending:
                if _decode(row).updated_at > timestamp:
                    raise ValueError("recovery timestamp cannot precede retained evidence")
            connection.execute(
                "DELETE FROM daily_digest_baselines WHERE calendar_date IN "
                "(SELECT calendar_date FROM digest_delivery_attempts WHERE phase IN ('preparing', 'sending'))"
            )
            connection.execute(
                "DELETE FROM daily_digest_reservations WHERE calendar_date IN "
                "(SELECT calendar_date FROM digest_delivery_attempts WHERE phase='preparing')"
            )
            connection.execute(
                "UPDATE digest_delivery_attempts SET phase='ready', updated_at=?, "
                "product_count=0, promotion_included=0, promotion_missing=0 WHERE phase='preparing'",
                (timestamp.isoformat(),),
            )
            connection.execute(
                "UPDATE digest_delivery_attempts SET phase='uncertain', updated_at=? WHERE phase='sending'",
                (timestamp.isoformat(),),
            )

    def claim(self, calendar_date: date, timestamp: datetime) -> Phase:
        """Reserve a date atomically; existing ambiguous dates cannot resend."""
        record = DigestDeliveryRecord(calendar_date, Phase.PREPARING, timestamp)
        key = calendar_date.isoformat()
        with self._session() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM digest_delivery_attempts WHERE calendar_date=?", (key,)).fetchone()
            if row is not None:
                previous = _decode(row)
                if timestamp < previous.updated_at:
                    raise ValueError("attempt timestamp cannot precede retained evidence")
                if previous.phase is not Phase.READY:
                    return previous.phase
            elif connection.execute("SELECT 1 FROM daily_digest_reservations WHERE calendar_date=?", (key,)).fetchone():
                record = DigestDeliveryRecord(calendar_date, Phase.LEGACY_RESERVED, timestamp)
            _write(connection, record)
            connection.execute(
                "INSERT OR IGNORE INTO daily_digest_reservations VALUES (?, ?)",
                (key, timestamp.isoformat()),
            )
            return record.phase

    def transition(
        self, calendar_date: date, expected: Phase, phase: Phase, timestamp: datetime, *,
        product_count: int = 0, promotion_included: bool = False, promotion_missing: bool = False,
    ) -> None:
        """Commit evidence only when the retained phase matches the caller."""
        record = DigestDeliveryRecord(calendar_date, phase, timestamp, product_count, promotion_included, promotion_missing)
        if not isinstance(expected, Phase):
            raise TypeError("expected must be a DigestDeliveryPhase")
        if (expected, phase) not in {
            (Phase.PREPARING, Phase.READY), (Phase.PREPARING, Phase.SENDING),
            (Phase.SENDING, Phase.READY), (Phase.SENDING, Phase.ACCEPTED), (Phase.SENDING, Phase.UNCERTAIN),
        }:
            raise ValueError("unsupported delivery transition")
        key = calendar_date.isoformat()
        with self._session() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM digest_delivery_attempts WHERE calendar_date=?", (key,)).fetchone()
            if row is None or _decode(row).phase is not expected:
                raise ValueError("delivery phase does not match expected evidence")
            if timestamp < _decode(row).updated_at:
                raise ValueError("transition timestamp cannot precede retained evidence")
            _write(connection, record)
            if phase in {Phase.READY, Phase.UNCERTAIN}:
                connection.execute("DELETE FROM daily_digest_baselines WHERE calendar_date=?", (key,))
            if phase is Phase.READY:
                connection.execute("DELETE FROM daily_digest_reservations WHERE calendar_date=?", (key,))

    def latest(self) -> DigestDeliveryRecord | None:
        """Return the newest local-date evidence with strict validation."""
        with self._session() as connection:
            row = connection.execute("SELECT * FROM digest_delivery_attempts ORDER BY calendar_date DESC LIMIT 1").fetchone()
            return None if row is None else _decode(row)

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = self._database.open()
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise DailyDigestReservationError("failed to open digest delivery evidence") from error
        try:
            yield connection
        except (sqlite3.Error, SqlitePersistenceError, TypeError, ValueError) as error:
            raise DailyDigestReservationError("daily digest delivery evidence failed") from error
        finally:
            try:
                self._database.close(connection)
            except SqlitePersistenceError as error:
                raise DailyDigestReservationError("failed to close digest delivery evidence") from error


def _write(connection: sqlite3.Connection, record: DigestDeliveryRecord) -> None:
    connection.execute(
        "INSERT INTO digest_delivery_attempts VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(calendar_date) DO UPDATE SET phase=excluded.phase, updated_at=excluded.updated_at, "
        "product_count=excluded.product_count, promotion_included=excluded.promotion_included, promotion_missing=excluded.promotion_missing",
        (record.calendar_date.isoformat(), record.phase.value, record.updated_at.isoformat(),
         record.product_count, int(record.promotion_included), int(record.promotion_missing)),
    )


def _decode(row: tuple[object, ...]) -> DigestDeliveryRecord:
    if row[4] not in (0, 1) or row[5] not in (0, 1):
        raise ValueError("invalid persisted promotion flags")
    record = DigestDeliveryRecord(date.fromisoformat(row[0]), Phase(row[1]), datetime.fromisoformat(row[2]), row[3], bool(row[4]), bool(row[5]))
    if record.calendar_date.isoformat() != row[0] or record.updated_at.isoformat() != row[2]:
        raise ValueError("delivery evidence must use canonical dates")
    return record


def _timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
