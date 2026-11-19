"""Read-only streaming price analysis using indexed retained observations."""

import json
import sqlite3
from datetime import datetime, tzinfo
from pathlib import Path

from core.pricing import PriceHistoryAssessment, PriceHistoryEngine
from core.state import StateSnapshot, StateStoreError
from infrastructure.persistence.snapshot_codec import SnapshotCodecError, decode_snapshot
from infrastructure.persistence.sqlite.database import SqliteDatabase, SqlitePersistenceError, validate_store_configuration


class SqlitePriceHistoryAssessmentSource:
    """Assess selected products without materializing a catalog history graph."""

    def __init__(self, path: Path, timezone: tzinfo, timeout_seconds: int = 5) -> None:
        """Configure the existing database and injected calendar timezone."""
        self._database = SqliteDatabase(validate_store_configuration(path, timeout_seconds), timeout_seconds)
        self._engine = PriceHistoryEngine(timezone)

    def assess(
        self, snapshots: tuple[StateSnapshot, ...], timestamp: datetime,
    ) -> tuple[PriceHistoryAssessment, ...]:
        """Stream exact observations only for the requested product IDs."""
        if not isinstance(snapshots, tuple) or not all(isinstance(s, StateSnapshot) for s in snapshots):
            raise TypeError("snapshots must be a tuple of StateSnapshot")
        if len({s.product.id for s in snapshots}) != len(snapshots):
            raise ValueError("snapshots must identify unique products")
        if not isinstance(timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        try:
            connection = self._database.open()
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise StateStoreError("failed to open price history") from error
        try:
            results = []
            for snapshot in snapshots:
                identifier = str(snapshot.product.id.value)
                cursor = connection.execute(
                    "SELECT snapshot FROM observations WHERE product_id=? ORDER BY sequence", (identifier,),
                )
                history = (decode_snapshot(json.loads(row[0]), identifier) for row in cursor)
                results.append(self._engine.assess(snapshot, history, timestamp))
            return tuple(results)
        except (json.JSONDecodeError, SnapshotCodecError, TypeError, ValueError) as error:
            raise StateStoreError("invalid persisted price history") from error
        except sqlite3.Error as error:
            raise StateStoreError("failed to read price history") from error
        finally:
            try:
                self._database.close(connection)
            except SqlitePersistenceError as error:
                raise StateStoreError("failed to close price history") from error
