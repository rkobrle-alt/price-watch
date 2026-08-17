"""Tests for durable SQLite operational state persistence."""

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest

from core.operations import (
    DailyDigestDelivery,
    OperationalFailureKind,
    OperationalHealthStatus,
    OperationalNotificationKind,
    OperationalState,
    OperationalStateError,
)
from infrastructure.persistence.sqlite import (
    SqliteOperationalStateStore,
)
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
)
from tests.unit.persistence.sqlite_helpers import open_database

NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)


def _state() -> OperationalState:
    return OperationalState(
        OperationalHealthStatus.FAILED,
        OperationalFailureKind.PROVIDER_DATA_INCOMPATIBLE,
        4,
        NOW,
        NOW,
        None,
        False,
        OperationalNotificationKind.FAILURE,
        DailyDigestDelivery(date(2026, 8, 14), NOW, 12, True),
    )


def test_store_initializes_lazily_and_returns_initial_state(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteOperationalStateStore(path)

    assert not path.exists()
    assert store.load() == OperationalState.initial()
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        assert connection.execute(
            "SELECT COUNT(*) FROM operational_state"
        ).fetchone() == (0,)


def test_store_round_trips_and_replaces_exact_state(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    first = _state()
    second = OperationalState.initial()
    store = SqliteOperationalStateStore(path)

    store.save(first)
    assert store.load() == first
    store.save(second)

    assert store.load() == second
    with open_database(path) as connection:
        rows = connection.execute("SELECT id, payload FROM operational_state").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    assert '"schema_version":1' in rows[0][1]


def test_version_four_schema_migrates_to_six(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    SqliteOperationalStateStore(path).load()
    with open_database(path) as connection:
        connection.execute("DROP TABLE operational_state")
        connection.execute("DROP TABLE daily_digest_baselines")
        connection.execute("PRAGMA user_version = 4")
        connection.commit()

    assert SqliteOperationalStateStore(path).load() == OperationalState.initial()
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(operational_state)"
            ).fetchall()
        )
    assert columns == ("id", "payload")


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        '{"schema_version":2}',
        '{"schema_version":1}',
        (
            '{"consecutive_failure_cycles":0,"failure_kind":null,'
            '"incident_notified":false,"incident_started_at":null,'
            '"last_checked_at":null,"last_digest_delivery":null,'
            '"last_recovered_at":null,"pending_notification":null,'
            '"schema_version":1,"status":"unknown"}'
        ),
        (
            '{"consecutive_failure_cycles":0,"failure_kind":null,'
            '"incident_notified":false,"incident_started_at":null,'
            '"last_checked_at":null,"last_digest_delivery":{"x":1},'
            '"last_recovered_at":null,"pending_notification":null,'
            '"schema_version":1,"status":"ok"}'
        ),
    ],
)
def test_store_rejects_malformed_persisted_document(
    tmp_path: Path,
    payload: str,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    SqliteOperationalStateStore(path).load()
    with open_database(path) as connection:
        connection.execute(
            "INSERT INTO operational_state (id, payload) VALUES (1, ?)",
            (payload,),
        )
        connection.commit()

    with pytest.raises(OperationalStateError, match="invalid persisted"):
        SqliteOperationalStateStore(path).load()


def test_store_rejects_invalid_public_arguments(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="path"):
        SqliteOperationalStateStore(cast(Path, "state.sqlite3"))
    with pytest.raises(TypeError, match="timeout"):
        SqliteOperationalStateStore(tmp_path / "state.sqlite3", True)
    with pytest.raises(ValueError, match="greater than zero"):
        SqliteOperationalStateStore(tmp_path / "state.sqlite3", 0)
    with pytest.raises(TypeError, match="state"):
        SqliteOperationalStateStore(tmp_path / "state.sqlite3").save(
            cast(OperationalState, object())
        )


def test_incompatible_version_five_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    SqliteOperationalStateStore(path).load()
    with open_database(path) as connection:
        connection.execute("DROP TABLE operational_state")
        connection.execute(
            "CREATE TABLE operational_state (id INTEGER PRIMARY KEY)"
        )
        connection.commit()

    with pytest.raises(OperationalStateError, match="load"):
        SqliteOperationalStateStore(path).load()


def _valid_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ok",
        "failure_kind": None,
        "consecutive_failure_cycles": 0,
        "incident_started_at": None,
        "last_checked_at": None,
        "last_recovered_at": None,
        "incident_notified": False,
        "pending_notification": None,
        "last_digest_delivery": None,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"failure_kind": 1},
        {"last_checked_at": 1},
        {
            "last_digest_delivery": {
                "calendar_date": 1,
                "delivered_at": NOW.isoformat(),
                "product_count": 1,
                "promotion_included": False,
            }
        },
        {
            "last_digest_delivery": {
                "calendar_date": "2026-08-14",
                "delivered_at": 1,
                "product_count": 1,
                "promotion_included": False,
            }
        },
    ],
)
def test_store_rejects_well_shaped_invalid_values(
    tmp_path: Path,
    change: dict[str, object],
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteOperationalStateStore(path)
    store.load()
    document = _valid_document()
    document.update(change)
    with open_database(path) as connection:
        connection.execute(
            "INSERT INTO operational_state (id, payload) VALUES (1, ?)",
            (json.dumps(document),),
        )
        connection.commit()

    with pytest.raises(OperationalStateError, match="invalid persisted"):
        store.load()


@pytest.mark.parametrize(
    "rows",
    [
        [(2, "payload")],
        [(1, 2)],
        [(1, "payload"), (1, "payload")],
    ],
)
def test_store_rejects_invalid_singleton_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rows: list[tuple[object, object]],
) -> None:
    class _Cursor:
        def fetchall(self) -> list[tuple[object, object]]:
            return rows

    class _Connection:
        def execute(self, statement: str) -> _Cursor:
            return _Cursor()

    store = SqliteOperationalStateStore(tmp_path / "catalog.sqlite3")
    monkeypatch.setattr(
        store._database,
        "open",
        lambda: cast(sqlite3.Connection, _Connection()),
    )
    monkeypatch.setattr(store._database, "close", lambda connection: None)

    with pytest.raises(OperationalStateError, match="invalid persisted"):
        store.load()


@pytest.mark.parametrize("operation", ["load", "save"])
def test_store_wraps_sqlite_operation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    failure = sqlite3.OperationalError("query failed")

    class _Connection:
        def __enter__(self) -> "_Connection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, *args: object) -> object:
            raise failure

    store = SqliteOperationalStateStore(tmp_path / "catalog.sqlite3")
    monkeypatch.setattr(
        store._database,
        "open",
        lambda: cast(sqlite3.Connection, _Connection()),
    )
    monkeypatch.setattr(store._database, "close", lambda connection: None)

    with pytest.raises(OperationalStateError) as captured:
        if operation == "load":
            store.load()
        else:
            store.save(OperationalState.initial())
    assert captured.value.__cause__ is failure


def test_store_wraps_open_and_close_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SqliteOperationalStateStore(tmp_path / "catalog.sqlite3")
    open_failure = SqlitePersistenceError("open failed")
    monkeypatch.setattr(
        store._database,
        "open",
        lambda: (_ for _ in ()).throw(open_failure),
    )
    with pytest.raises(OperationalStateError, match="load") as captured:
        store.load()
    assert captured.value.__cause__ is open_failure

    monkeypatch.undo()
    store.load()
    close_failure = SqlitePersistenceError("close failed")

    def fail_close(connection: sqlite3.Connection) -> None:
        connection.close()
        raise close_failure

    monkeypatch.setattr(store._database, "close", fail_close)
    with pytest.raises(OperationalStateError, match="close") as captured:
        store.load()
    assert captured.value.__cause__ is close_failure


def test_unsupported_schema_and_failed_v4_migration_are_wrapped(
    tmp_path: Path,
) -> None:
    unsupported = tmp_path / "unsupported.sqlite3"
    SqliteOperationalStateStore(unsupported).load()
    with open_database(unsupported) as connection:
        connection.execute("PRAGMA user_version = 7")
        connection.commit()
    with pytest.raises(OperationalStateError, match="load"):
        SqliteOperationalStateStore(unsupported).load()

    conflicting = tmp_path / "conflicting.sqlite3"
    SqliteOperationalStateStore(conflicting).load()
    with open_database(conflicting) as connection:
        connection.execute("DROP TABLE operational_state")
        connection.execute(
            "CREATE TABLE operational_state (wrong TEXT)"
        )
        connection.execute("PRAGMA user_version = 4")
        connection.commit()
    with pytest.raises(OperationalStateError, match="load"):
        SqliteOperationalStateStore(conflicting).load()
    with open_database(conflicting) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (4,)
