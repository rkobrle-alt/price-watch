"""SQLite latest-state and exact observation-history implementation."""

import json
import sqlite3
from pathlib import Path

from core.domain import ProductId
from core.state import ObservationStatistics, StateSnapshot, StateStoreError
from infrastructure.persistence.snapshot_codec import (
    SnapshotCodecError,
    decode_snapshot,
    encode_snapshot,
)
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    validate_store_configuration,
)


class SqliteStateStore:
    """Append exact observations while exposing the latest product state."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Validate configuration without opening or creating the database."""
        validated_path = validate_store_configuration(path, timeout_seconds)
        self._database = SqliteDatabase(validated_path, timeout_seconds)

    def load(self, product_id: ProductId) -> StateSnapshot | None:
        """Return the last inserted observation for a product identifier."""
        _validate_product_id(product_id)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._database.open()
            row = connection.execute(
                "SELECT snapshot FROM observations WHERE product_id = ? "
                "ORDER BY sequence DESC LIMIT 1",
                (str(product_id.value),),
            ).fetchone()
            if row is None:
                return None
            return _decode_payload(row[0], str(product_id.value))
        except (json.JSONDecodeError, SnapshotCodecError) as error:
            raise StateStoreError("invalid persisted SQLite observation") from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise StateStoreError("failed to load SQLite product state") from error
        finally:
            if connection is not None:
                _close_state_connection(self._database, connection)

    def save(self, snapshot: StateSnapshot) -> None:
        """Append one exact product observation transactionally."""
        if not isinstance(snapshot, StateSnapshot):
            raise TypeError("snapshot must be a StateSnapshot")
        payload = json.dumps(
            encode_snapshot(snapshot),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            connection = self._database.open()
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise StateStoreError("failed to save SQLite product state") from error
        try:
            with connection:
                connection.execute(
                    "INSERT INTO observations (product_id, snapshot) VALUES (?, ?)",
                    (str(snapshot.product.id.value), payload),
                )
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise StateStoreError("failed to save SQLite product state") from error
        finally:
            _close_state_connection(self._database, connection)

    def history(
        self,
        product_id: ProductId,
        limit: int | None = None,
    ) -> tuple[StateSnapshot, ...]:
        """Return all or the newest bounded observations chronologically."""
        _validate_product_id(product_id)
        _validate_limit(limit)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._database.open()
            if limit is None:
                rows = connection.execute(
                    "SELECT snapshot FROM observations WHERE product_id = ? "
                    "ORDER BY sequence",
                    (str(product_id.value),),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT snapshot FROM ("
                    "SELECT sequence, snapshot FROM observations "
                    "WHERE product_id = ? ORDER BY sequence DESC LIMIT ?"
                    ") ORDER BY sequence",
                    (str(product_id.value), limit),
                ).fetchall()
            return tuple(
                _decode_payload(row[0], str(product_id.value)) for row in rows
            )
        except (json.JSONDecodeError, SnapshotCodecError) as error:
            raise StateStoreError("invalid persisted SQLite observation") from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise StateStoreError("failed to read SQLite observation history") from error
        finally:
            if connection is not None:
                _close_state_connection(self._database, connection)

    def latest_snapshots(self) -> tuple[StateSnapshot, ...]:
        """Return one last-inserted snapshot per product in ID order."""
        connection: sqlite3.Connection | None = None
        try:
            connection = self._database.open()
            rows = connection.execute(
                "SELECT observations.product_id, observations.snapshot "
                "FROM observations JOIN ("
                "SELECT product_id, MAX(sequence) AS latest_sequence "
                "FROM observations GROUP BY product_id"
                ") AS latest ON observations.sequence = latest.latest_sequence "
                "ORDER BY observations.product_id"
            ).fetchall()
            return tuple(_decode_payload(row[1], row[0]) for row in rows)
        except (json.JSONDecodeError, SnapshotCodecError) as error:
            raise StateStoreError("invalid persisted SQLite observation") from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise StateStoreError("failed to read latest SQLite states") from error
        finally:
            if connection is not None:
                _close_state_connection(self._database, connection)

    def observation_statistics(self) -> ObservationStatistics:
        """Return read-only counts, boundary timestamps and allocated bytes."""
        connection: sqlite3.Connection | None = None
        try:
            connection = self._database.open()
            aggregate = connection.execute(
                "SELECT COUNT(*), COUNT(DISTINCT product_id), "
                "MIN(sequence), MAX(sequence) FROM observations"
            ).fetchone()
            observation_count = aggregate[0]
            observed_product_count = aggregate[1]
            first_at = None
            last_at = None
            if observation_count:
                rows = connection.execute(
                    "SELECT product_id, snapshot FROM observations "
                    "WHERE sequence IN (?, ?) ORDER BY sequence",
                    (aggregate[2], aggregate[3]),
                ).fetchall()
                snapshots = tuple(
                    _decode_payload(row[1], row[0]) for row in rows
                )
                first_at = snapshots[0].timestamp
                last_at = snapshots[-1].timestamp
            storage_size_bytes = _allocated_database_bytes(connection)
            reclaimable_size_bytes = _reclaimable_database_bytes(connection)
            return ObservationStatistics(
                observation_count=observation_count,
                observed_product_count=observed_product_count,
                first_observation_at=first_at,
                last_observation_at=last_at,
                storage_size_bytes=storage_size_bytes,
                reclaimable_size_bytes=reclaimable_size_bytes,
            )
        except (
            json.JSONDecodeError,
            SnapshotCodecError,
            TypeError,
            ValueError,
        ) as error:
            raise StateStoreError(
                "invalid persisted SQLite observation statistics"
            ) from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise StateStoreError(
                "failed to read SQLite observation statistics"
            ) from error
        finally:
            if connection is not None:
                _close_state_connection(self._database, connection)


def _validate_product_id(product_id: object) -> None:
    if not isinstance(product_id, ProductId):
        raise TypeError("product_id must be a ProductId")


def _validate_limit(limit: object) -> None:
    if limit is None:
        return
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an int or None")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")


def _decode_payload(value: object, product_id: str) -> StateSnapshot:
    if not isinstance(value, str):
        raise SnapshotCodecError("SQLite snapshot must be a JSON string")
    return decode_snapshot(json.loads(value), product_id)


def _allocated_database_bytes(connection: sqlite3.Connection) -> int:
    page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    if isinstance(page_count, bool) or not isinstance(page_count, int):
        raise TypeError("SQLite page count must be an int")
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise TypeError("SQLite page size must be an int")
    if page_count < 0 or page_size <= 0:
        raise ValueError("SQLite page metrics must be positive")
    return page_count * page_size


def _reclaimable_database_bytes(connection: sqlite3.Connection) -> int:
    free_page_count = connection.execute("PRAGMA freelist_count").fetchone()[0]
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    if isinstance(free_page_count, bool) or not isinstance(free_page_count, int):
        raise TypeError("SQLite free page count must be an int")
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise TypeError("SQLite page size must be an int")
    if free_page_count < 0 or page_size <= 0:
        raise ValueError("SQLite free page metrics must be non-negative")
    return free_page_count * page_size


def _close_state_connection(
    database: SqliteDatabase,
    connection: sqlite3.Connection,
) -> None:
    try:
        database.close(connection)
    except SqlitePersistenceError as error:
        raise StateStoreError("failed to close state database") from error
