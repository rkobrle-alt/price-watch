"""Regression for history-sized memory amplification in retention previews."""

import json
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from infrastructure.persistence.snapshot_codec import encode_snapshot
from infrastructure.persistence.sqlite import (
    SqliteObservationRetentionManager,
    SqliteStateStore,
)
from tests.unit.persistence.helpers import create_snapshot
from tests.unit.persistence.sqlite_helpers import open_database


@pytest.mark.parametrize("recent", [False, True])
def test_preview_memory_does_not_materialize_observation_history(
    tmp_path: Path, recent: bool,
) -> None:
    """Thousands of observations must not retain thousands of domain graphs."""
    path = tmp_path / "catalog.sqlite3"
    cutoff = datetime(2026, 11, 11, tzinfo=UTC)
    timestamp = cutoff if recent else cutoff - timedelta(days=1)
    snapshot = create_snapshot(timestamp=timestamp)
    payload = json.dumps(encode_snapshot(snapshot))
    SqliteStateStore(path).save(snapshot)
    with open_database(path) as connection:
        connection.executemany(
            "INSERT INTO observations(product_id, snapshot) VALUES (?, ?)",
            ((str(snapshot.product.id.value), payload) for _ in range(7999)),
        )
        connection.commit()

    tracemalloc.start()
    try:
        plan = SqliteObservationRetentionManager(path).plan(cutoff)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert plan.observation_count == 8000
    assert plan.removable_observation_count == (0 if recent else 7998)
    assert plan.protected_observation_count == (0 if recent else 2)
    assert peak < 4 * 1024 * 1024, f"preview allocated {peak:,} bytes"
