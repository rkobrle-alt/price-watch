"""Focused failure tests for the private SQLite lifecycle boundary."""

import sqlite3
from pathlib import Path
from typing import cast

import pytest

from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    _close_after_failed_open,
    _create_schema,
    _read_user_version,
)


class _Cursor:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class _InvalidVersionConnection:
    def execute(self, statement: str) -> _Cursor:
        return _Cursor(None)


class _FailingConnection:
    def __init__(self, failure: sqlite3.Error) -> None:
        self._failure = failure

    def __enter__(self) -> "_FailingConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: str) -> _Cursor:
        raise self._failure

    def close(self) -> None:
        raise self._failure


def test_invalid_pragma_result_is_rejected() -> None:
    connection = cast(sqlite3.Connection, _InvalidVersionConnection())

    with pytest.raises(SqlitePersistenceError, match="version"):
        _read_user_version(connection)


def test_schema_initialization_failure_preserves_cause() -> None:
    failure = sqlite3.OperationalError("create failed")
    connection = cast(sqlite3.Connection, _FailingConnection(failure))

    with pytest.raises(SqlitePersistenceError, match="initialize") as captured:
        _create_schema(connection)

    assert captured.value.__cause__ is failure


def test_database_close_failure_preserves_cause() -> None:
    failure = sqlite3.OperationalError("close failed")
    connection = cast(sqlite3.Connection, _FailingConnection(failure))

    with pytest.raises(SqlitePersistenceError, match="close") as captured:
        SqliteDatabase(Path("unused.sqlite3"), 5).close(connection)

    assert captured.value.__cause__ is failure


def test_failed_open_cleanup_ignores_secondary_close_failure() -> None:
    failure = sqlite3.OperationalError("close failed")
    connection = cast(sqlite3.Connection, _FailingConnection(failure))

    assert _close_after_failed_open(connection) is None
