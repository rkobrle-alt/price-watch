"""Behavior tests for manual SQLite observation retention."""

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from core.domain import Currency, Money
from core.state import ObservationRetentionManager, StateSnapshot, StateStoreError
from infrastructure.persistence.snapshot_codec import SnapshotCodecError
from infrastructure.persistence.sqlite import (
    SqliteObservationRetentionManager,
    SqliteStateStore,
)
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
)
from infrastructure.persistence.sqlite.retention import (
    _close_connection,
    _decode_row,
    _rollback,
    _write_new_backup,
)
from tests.unit.persistence.helpers import (
    OTHER_PRODUCT_ID,
    PRODUCT_ID,
    create_snapshot,
)
from tests.unit.persistence.sqlite_helpers import open_database

_CUTOFF = datetime(2026, 8, 1, tzinfo=UTC)


def _snapshot(
    amount: str,
    timestamp: datetime,
    *,
    product_id=PRODUCT_ID,
    currency: Currency = Currency.EUR,
) -> StateSnapshot:
    snapshot = create_snapshot(
        product_id=product_id,
        amount=amount,
        timestamp=timestamp,
    )
    product = replace(
        snapshot.product,
        current_price=Money(Decimal(amount), currency),
        original_price=None,
    )
    return StateSnapshot(product, timestamp)


def _populate_retention_scenario(path: Path) -> tuple[StateSnapshot, ...]:
    observations = (
        _snapshot("80", _CUTOFF - timedelta(days=3)),
        _snapshot("100", _CUTOFF - timedelta(days=2)),
        _snapshot("100", _CUTOFF - timedelta(days=1)),
        _snapshot("50", _CUTOFF - timedelta(days=4), currency=Currency.USD),
        _snapshot(
            "40",
            _CUTOFF - timedelta(days=5),
            product_id=OTHER_PRODUCT_ID,
        ),
        _snapshot("90", _CUTOFF),
        _snapshot("70", _CUTOFF - timedelta(days=6)),
    )
    store = SqliteStateStore(path)
    for snapshot in observations:
        store.save(snapshot)
    return observations


def test_constructor_has_no_io_and_implements_protocol(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "catalog.sqlite3"
    manager: ObservationRetentionManager = SqliteObservationRetentionManager(path)

    assert isinstance(manager, SqliteObservationRetentionManager)
    assert not path.parent.exists()


def test_plan_is_read_only_and_preserves_required_rows(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    observations = _populate_retention_scenario(path)
    before = path.read_bytes()

    plan = SqliteObservationRetentionManager(path).plan(_CUTOFF)

    assert plan.observation_count == 7
    assert plan.removable_observation_count == 2
    assert plan.retained_observation_count == 5
    assert plan.protected_observation_count == 4
    assert path.read_bytes() == before
    assert SqliteStateStore(path).history(PRODUCT_ID) == tuple(
        observation
        for observation in observations
        if observation.product.id == PRODUCT_ID
    )


def test_empty_and_all_recent_plans_remove_nothing(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    manager = SqliteObservationRetentionManager(path)

    assert manager.plan(_CUTOFF).observation_count == 0
    SqliteStateStore(path).save(_snapshot("10", _CUTOFF))

    plan = manager.plan(_CUTOFF)
    assert plan.removable_observation_count == 0
    assert plan.retained_observation_count == 1
    assert plan.protected_observation_count == 0


def test_apply_backs_up_complete_database_then_deletes_only_planned_rows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    observations = _populate_retention_scenario(path)
    backup = tmp_path / "backups" / "before.sqlite3"
    manager = SqliteObservationRetentionManager(path)

    result = manager.apply(_CUTOFF, backup)

    assert result.plan.removable_observation_count == 2
    assert result.backup_file == backup
    assert backup.exists()
    assert len(SqliteStateStore(backup).history(PRODUCT_ID)) == 6
    retained = SqliteStateStore(path).history(PRODUCT_ID)
    assert retained == (
        observations[1],
        observations[3],
        observations[5],
        observations[6],
    )
    assert SqliteStateStore(path).history(OTHER_PRODUCT_ID) == (observations[4],)
    assert SqliteStateStore(path).load(PRODUCT_ID) == observations[6]
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (4,)
        assert connection.execute(
            "SELECT COUNT(*) FROM notification_reservations"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM daily_digest_reservations"
        ).fetchone() == (0,)


def test_repeated_plan_after_apply_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    _populate_retention_scenario(path)
    manager = SqliteObservationRetentionManager(path)
    manager.apply(_CUTOFF, tmp_path / "first.sqlite3")

    plan = manager.plan(_CUTOFF)

    assert plan.observation_count == 5
    assert plan.removable_observation_count == 0


@pytest.mark.parametrize(
    ("cutoff", "exception_type", "message"),
    [
        ("now", TypeError, "cutoff"),
        (datetime(2026, 8, 1), ValueError, "timezone-aware"),
    ],
)
def test_methods_reject_invalid_cutoff_before_io(
    tmp_path: Path,
    cutoff: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    manager = SqliteObservationRetentionManager(path)

    with pytest.raises(exception_type, match=message):
        manager.plan(cast(datetime, cutoff))
    with pytest.raises(exception_type, match=message):
        manager.apply(cast(datetime, cutoff), tmp_path / "backup.sqlite3")
    assert not path.exists()


def test_apply_rejects_invalid_or_source_backup_path_before_io(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    manager = SqliteObservationRetentionManager(path)

    with pytest.raises(TypeError, match="backup_file"):
        manager.apply(_CUTOFF, cast(Path, "backup.sqlite3"))
    with pytest.raises(ValueError, match="differ"):
        manager.apply(_CUTOFF, path)
    assert not path.exists()


def test_existing_backup_is_never_overwritten_or_applied(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    _populate_retention_scenario(path)
    backup = tmp_path / "backup.sqlite3"
    backup.write_bytes(b"existing")

    with pytest.raises(StateStoreError, match="failed to apply") as captured:
        SqliteObservationRetentionManager(path).apply(_CUTOFF, backup)

    assert isinstance(captured.value.__cause__, FileExistsError)
    assert backup.read_bytes() == b"existing"
    assert len(SqliteStateStore(path).history(PRODUCT_ID)) == 6


def test_malformed_snapshot_prevents_plan_and_apply(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    SqliteStateStore(path).save(_snapshot("10", _CUTOFF - timedelta(days=2)))
    with open_database(path) as connection:
        connection.execute("UPDATE observations SET snapshot = '{broken'")
        connection.commit()
    manager = SqliteObservationRetentionManager(path)

    with pytest.raises(StateStoreError, match="invalid persisted") as plan_error:
        manager.plan(_CUTOFF)
    with pytest.raises(StateStoreError, match="invalid persisted") as apply_error:
        manager.apply(_CUTOFF, tmp_path / "backup.sqlite3")

    assert plan_error.value.__cause__ is not None
    assert apply_error.value.__cause__ is not None
    assert not (tmp_path / "backup.sqlite3").exists()


def test_logical_deletion_exposes_reclaimable_pages(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteStateStore(path)
    for index in range(120):
        store.save(
            _snapshot(
                str(index + 1),
                _CUTOFF - timedelta(days=120 - index),
            )
        )

    SqliteObservationRetentionManager(path).apply(
        _CUTOFF,
        tmp_path / "backup.sqlite3",
    )
    statistics = store.observation_statistics()

    assert statistics.observation_count == 1
    assert statistics.reclaimable_size_bytes > 0
    assert statistics.reclaimable_size_bytes <= statistics.storage_size_bytes


def test_query_failure_is_wrapped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    failure = sqlite3.OperationalError("query failed")

    class _Connection:
        def execute(self, statement: str) -> object:
            raise failure

    monkeypatch.setattr(
        "infrastructure.persistence.sqlite.retention.SqliteDatabase.open",
        lambda database: _Connection(),
    )
    monkeypatch.setattr(
        "infrastructure.persistence.sqlite.retention.SqliteDatabase.close",
        lambda database, connection: None,
    )

    with pytest.raises(StateStoreError, match="failed to plan") as captured:
        SqliteObservationRetentionManager(tmp_path / "catalog.sqlite3").plan(
            _CUTOFF
        )

    assert captured.value.__cause__ is failure


@pytest.mark.parametrize(
    "row",
    [
        object(),
        (),
        (True, str(PRODUCT_ID.value), "{}"),
        (0, str(PRODUCT_ID.value), "{}"),
        ("1", str(PRODUCT_ID.value), "{}"),
        (1, 1, "{}"),
        (1, str(PRODUCT_ID.value), sqlite3.Binary(b"payload")),
    ],
)
def test_invalid_raw_retention_rows_are_rejected(row: object) -> None:
    with pytest.raises(SnapshotCodecError, match="SQLite|invalid"):
        _decode_row(row)


def test_failed_backup_write_removes_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "backup.sqlite3"
    failure = OSError("fsync failed")
    monkeypatch.setattr(
        "infrastructure.persistence.sqlite.retention.os.fsync",
        lambda descriptor: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(OSError) as captured:
        _write_new_backup(path, b"database")

    assert captured.value is failure
    assert not path.exists()


def test_backup_cleanup_failure_preserves_original_write_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "backup.sqlite3"
    failure = OSError("fsync failed")
    monkeypatch.setattr(
        "infrastructure.persistence.sqlite.retention.os.fsync",
        lambda descriptor: (_ for _ in ()).throw(failure),
    )
    monkeypatch.setattr(Path, "unlink", lambda value: (_ for _ in ()).throw(
        OSError("unlink failed")
    ))

    with pytest.raises(OSError) as captured:
        _write_new_backup(path, b"database")

    assert captured.value is failure
    assert path.exists()


def test_rollback_handles_absent_connection_and_sqlite_failure() -> None:
    class _Connection:
        def rollback(self) -> None:
            raise sqlite3.OperationalError("rollback failed")

    assert _rollback(None) is None
    assert _rollback(cast(sqlite3.Connection, _Connection())) is None


def test_close_failure_is_translated(tmp_path: Path) -> None:
    failure = SqlitePersistenceError("close failed")

    class _Database:
        def close(self, connection: sqlite3.Connection) -> None:
            raise failure

    with pytest.raises(StateStoreError, match="failed to close") as captured:
        _close_connection(
            cast(SqliteDatabase, _Database()),
            cast(sqlite3.Connection, object()),
        )

    assert captured.value.__cause__ is failure
