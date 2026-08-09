"""Manual backup-protected retention for SQLite observation history."""

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from core.state import (
    ObservationRetentionPlan,
    ObservationRetentionResult,
    StateSnapshot,
    StateStoreError,
)
from core.state.retention import validate_retention_cutoff
from infrastructure.persistence.snapshot_codec import (
    SnapshotCodecError,
    decode_snapshot,
)
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    validate_store_configuration,
)


@dataclass(frozen=True, slots=True)
class _StoredObservation:
    sequence: int
    snapshot: StateSnapshot


@dataclass(frozen=True, slots=True)
class _RetentionSelection:
    plan: ObservationRetentionPlan
    removable_sequences: tuple[int, ...]


class SqliteObservationRetentionManager:
    """Plan and explicitly apply safe SQLite observation retention."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Validate configuration without opening or creating the database."""
        validated_path = validate_store_configuration(path, timeout_seconds)
        self._path = validated_path
        self._database = SqliteDatabase(validated_path, timeout_seconds)

    def plan(self, cutoff: datetime) -> ObservationRetentionPlan:
        """Return protected and removable counts without mutating SQLite."""
        validated_cutoff = validate_retention_cutoff(cutoff)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._database.open()
            return _select_retention(connection, validated_cutoff).plan
        except (
            json.JSONDecodeError,
            SnapshotCodecError,
            TypeError,
            ValueError,
        ) as error:
            raise StateStoreError(
                "invalid persisted SQLite observation retention data"
            ) from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise StateStoreError("failed to plan SQLite observation retention") from error
        finally:
            if connection is not None:
                _close_connection(self._database, connection)

    def apply(
        self,
        cutoff: datetime,
        backup_file: Path,
    ) -> ObservationRetentionResult:
        """Create a complete backup and transactionally remove planned rows."""
        validated_cutoff = validate_retention_cutoff(cutoff)
        validated_backup = _validate_backup_file(self._path, backup_file)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._database.open()
            connection.execute("BEGIN IMMEDIATE")
            selection = _select_retention(connection, validated_cutoff)
            _write_new_backup(validated_backup, connection.serialize())
            connection.executemany(
                "DELETE FROM observations WHERE sequence = ?",
                ((sequence,) for sequence in selection.removable_sequences),
            )
            connection.commit()
            return ObservationRetentionResult(selection.plan, validated_backup)
        except (
            json.JSONDecodeError,
            SnapshotCodecError,
            TypeError,
            ValueError,
        ) as error:
            _rollback(connection)
            raise StateStoreError(
                "invalid persisted SQLite observation retention data"
            ) from error
        except (OSError, sqlite3.Error, SqlitePersistenceError) as error:
            _rollback(connection)
            raise StateStoreError("failed to apply SQLite observation retention") from error
        finally:
            if connection is not None:
                _close_connection(self._database, connection)


def _select_retention(
    connection: sqlite3.Connection,
    cutoff: datetime,
) -> _RetentionSelection:
    rows = connection.execute(
        "SELECT sequence, product_id, snapshot FROM observations ORDER BY sequence"
    ).fetchall()
    observations = tuple(_decode_row(row) for row in rows)
    latest_sequences: dict[str, int] = {}
    maxima: dict[tuple[str, str], tuple[Decimal, int]] = {}
    recent_sequences: set[int] = set()
    all_sequences: set[int] = set()
    for observation in observations:
        sequence = observation.sequence
        product = observation.snapshot.product
        product_id = str(product.id.value)
        currency = product.current_price.currency.value
        amount = product.current_price.amount
        all_sequences.add(sequence)
        latest_sequences[product_id] = sequence
        if observation.snapshot.timestamp >= cutoff:
            recent_sequences.add(sequence)
        maximum_key = (product_id, currency)
        maximum = maxima.get(maximum_key)
        if maximum is None or amount > maximum[0]:
            maxima[maximum_key] = (amount, sequence)

    protected_sequences = set(latest_sequences.values())
    protected_sequences.update(value[1] for value in maxima.values())
    retained_sequences = recent_sequences | protected_sequences
    removable_sequences = tuple(sorted(all_sequences - retained_sequences))
    protected_old = protected_sequences - recent_sequences
    plan = ObservationRetentionPlan(
        cutoff=cutoff,
        observation_count=len(observations),
        removable_observation_count=len(removable_sequences),
        retained_observation_count=len(retained_sequences),
        protected_observation_count=len(protected_old),
    )
    return _RetentionSelection(plan, removable_sequences)


def _decode_row(row: object) -> _StoredObservation:
    if not isinstance(row, tuple) or len(row) != 3:
        raise SnapshotCodecError("invalid SQLite observation retention row")
    sequence, product_id, payload = row
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise SnapshotCodecError("invalid SQLite observation sequence")
    if not isinstance(product_id, str):
        raise SnapshotCodecError("invalid SQLite observation product ID")
    if not isinstance(payload, str):
        raise SnapshotCodecError("SQLite snapshot must be a JSON string")
    snapshot = decode_snapshot(json.loads(payload), product_id)
    return _StoredObservation(sequence, snapshot)


def _validate_backup_file(source: Path, backup_file: object) -> Path:
    if not isinstance(backup_file, Path):
        raise TypeError("backup_file must be a Path")
    if source.resolve(strict=False) == backup_file.resolve(strict=False):
        raise ValueError("backup_file must differ from the source database")
    return backup_file


def _write_new_backup(path: Path, payload: bytes) -> None:
    created = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            created = True
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        if created:
            _remove_partial_backup(path)
        raise


def _remove_partial_backup(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return


def _rollback(connection: sqlite3.Connection | None) -> None:
    if connection is None:
        return
    try:
        connection.rollback()
    except sqlite3.Error:
        return


def _close_connection(
    database: SqliteDatabase,
    connection: sqlite3.Connection,
) -> None:
    try:
        database.close(connection)
    except SqlitePersistenceError as error:
        raise StateStoreError("failed to close retention database") from error
