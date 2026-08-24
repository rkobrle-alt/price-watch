"""Tests for SQLite weekly operational summary persistence."""

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest

from core.operations import (
    OperationalFailureCount,
    OperationalFailureKind,
    OperationalStateError,
    WeeklyOperationalSummary,
)
from infrastructure.persistence.sqlite import SqliteWeeklyOperationalSummaryStore
from infrastructure.persistence.sqlite.database import SqlitePersistenceError
from tests.unit.persistence.sqlite_helpers import open_database

MONDAY = date(2026, 8, 17)
NOW = datetime(2026, 8, 17, 8, 0, tzinfo=UTC)


def _summary() -> WeeklyOperationalSummary:
    return WeeklyOperationalSummary(
        MONDAY,
        (OperationalFailureCount(OperationalFailureKind.PARTIAL_PROVIDER_FAILURE, 2),),
        2,
        1,
        1,
        2,
        0,
        NOW,
        NOW,
        NOW,
    )


def test_store_round_trips_replaces_and_returns_none(tmp_path: Path) -> None:
    store = SqliteWeeklyOperationalSummaryStore(tmp_path / "catalog.sqlite3")
    assert store.load(MONDAY) is None
    store.save(_summary())
    assert store.load(MONDAY) == _summary()
    replacement = WeeklyOperationalSummary(MONDAY)
    store.save(replacement)
    assert store.load(MONDAY) == replacement


def test_store_rejects_invalid_public_arguments(tmp_path: Path) -> None:
    store = SqliteWeeklyOperationalSummaryStore(tmp_path / "catalog.sqlite3")
    with pytest.raises(TypeError, match="period_start"):
        store.load(cast(date, datetime(2026, 8, 17)))
    with pytest.raises(TypeError, match="summary"):
        store.save(cast(WeeklyOperationalSummary, object()))


@pytest.mark.parametrize(
    "payload",
    (
        "not-json",
        "{}",
        '{"version":2}',
    ),
)
def test_store_translates_malformed_payload(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteWeeklyOperationalSummaryStore(path)
    store.save(WeeklyOperationalSummary(MONDAY))
    with open_database(path) as connection:
        connection.execute(
            "UPDATE weekly_operational_summaries SET payload = ?",
            (payload,),
        )
        connection.commit()
    with pytest.raises(OperationalStateError, match="load"):
        store.load(MONDAY)


def test_schema_six_migrates_and_preserves_existing_rows(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteWeeklyOperationalSummaryStore(path)
    store.save(_summary())
    with open_database(path) as connection:
        connection.execute("DROP TABLE weekly_operational_summaries")
        connection.execute("PRAGMA user_version = 6")
        connection.commit()
    assert store.load(MONDAY) is None
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(weekly_operational_summaries)"
            )
        )
    assert columns == ("period_start", "payload")


def test_incompatible_schema_seven_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    SqliteWeeklyOperationalSummaryStore(path).save(_summary())
    with open_database(path) as connection:
        connection.execute("DROP TABLE weekly_operational_summaries")
        connection.execute("CREATE TABLE weekly_operational_summaries (wrong TEXT)")
        connection.commit()
    with pytest.raises(OperationalStateError):
        SqliteWeeklyOperationalSummaryStore(path).load(MONDAY)


@pytest.mark.parametrize(
    "change",
    (
        {"version": 2},
        {"failure_counts": {}},
        {"failure_counts": [{}]},
        {"period_start": 1},
        {
            "failure_counts": [
                {"kind": "partial_provider_failure", "count": 1}
            ],
            "total_failed_cycles": 1,
            "first_failure_at": 1,
            "last_failure_at": NOW.isoformat(),
        },
    ),
)
def test_store_rejects_well_shaped_invalid_documents(
    tmp_path: Path,
    change: dict[str, object],
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteWeeklyOperationalSummaryStore(path)
    store.save(WeeklyOperationalSummary(MONDAY))
    document: dict[str, object] = {
        "version": 1,
        "period_start": MONDAY.isoformat(),
        "failure_counts": [],
        "total_failed_cycles": 0,
        "incident_count": 0,
        "recovery_count": 0,
        "longest_failure_streak": 0,
        "current_failure_streak": 0,
        "first_failure_at": None,
        "last_failure_at": None,
        "delivered_at": None,
    }
    document.update(change)
    with open_database(path) as connection:
        connection.execute(
            "UPDATE weekly_operational_summaries SET payload = ?",
            (json.dumps(document),),
        )
        connection.commit()

    with pytest.raises(OperationalStateError, match="load"):
        store.load(MONDAY)


def test_store_wraps_query_open_and_close_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Connection:
        def __enter__(self) -> "_Connection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, *args: object) -> object:
            raise sqlite3.OperationalError("query failed")

    store = SqliteWeeklyOperationalSummaryStore(tmp_path / "catalog.sqlite3")
    monkeypatch.setattr(
        store._database,
        "open",
        lambda: cast(sqlite3.Connection, _Connection()),
    )
    monkeypatch.setattr(store._database, "close", lambda connection: None)
    with pytest.raises(OperationalStateError, match="save"):
        store.save(WeeklyOperationalSummary(MONDAY))

    open_failure = SqlitePersistenceError("open failed")
    monkeypatch.setattr(
        store._database,
        "open",
        lambda: (_ for _ in ()).throw(open_failure),
    )
    with pytest.raises(OperationalStateError, match="load"):
        store.load(MONDAY)

    monkeypatch.undo()
    store.load(MONDAY)
    close_failure = SqlitePersistenceError("close failed")

    def fail_close(connection: sqlite3.Connection) -> None:
        connection.close()
        raise close_failure

    monkeypatch.setattr(store._database, "close", fail_close)
    with pytest.raises(OperationalStateError, match="close"):
        store.load(MONDAY)


def test_store_rejects_non_text_database_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Cursor:
        def fetchone(self) -> tuple[int]:
            return (1,)

    class _Connection:
        def execute(self, *args: object) -> _Cursor:
            return _Cursor()

    store = SqliteWeeklyOperationalSummaryStore(tmp_path / "catalog.sqlite3")
    monkeypatch.setattr(
        store._database,
        "open",
        lambda: cast(sqlite3.Connection, _Connection()),
    )
    monkeypatch.setattr(store._database, "close", lambda connection: None)
    with pytest.raises(OperationalStateError, match="load"):
        store.load(MONDAY)
