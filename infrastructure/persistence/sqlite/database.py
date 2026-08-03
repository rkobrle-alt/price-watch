"""Private versioned SQLite database lifecycle for durable stores."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_CATALOG_COLUMNS = (
    "sequence",
    "provider_id",
    "external_id",
    "url",
    "first_seen_at",
    "last_seen_at",
)
_OBSERVATION_COLUMNS = ("sequence", "product_id", "snapshot")


class SqlitePersistenceError(Exception):
    """Report an internal SQLite lifecycle or schema failure."""


class SqliteDatabase:
    """Open, initialize, validate and close one Price Watch database."""

    def __init__(self, path: Path, timeout_seconds: int) -> None:
        """Retain already validated connection configuration."""
        self._path = path
        self._timeout_seconds = timeout_seconds

    def open(self) -> sqlite3.Connection:
        """Open and validate a connection, initializing an empty database."""
        connection: sqlite3.Connection | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self._path,
                timeout=self._timeout_seconds,
            )
            self._initialize(connection)
            return connection
        except (OSError, sqlite3.Error, SqlitePersistenceError) as error:
            if connection is not None:
                _close_after_failed_open(connection)
            if isinstance(error, SqlitePersistenceError):
                raise
            raise SqlitePersistenceError("failed to open SQLite database") from error

    def close(self, connection: sqlite3.Connection) -> None:
        """Close one operation connection and translate close failures."""
        try:
            connection.close()
        except sqlite3.Error as error:
            raise SqlitePersistenceError("failed to close SQLite database") from error

    def _initialize(self, connection: sqlite3.Connection) -> None:
        version = _read_user_version(connection)
        tables = _user_tables(connection)
        if version == 0:
            if tables:
                raise SqlitePersistenceError(
                    "unversioned SQLite database contains user tables"
                )
            _create_schema(connection)
        elif version != SCHEMA_VERSION:
            raise SqlitePersistenceError(
                f"unsupported SQLite schema version: {version}"
            )
        _validate_schema(connection)


def validate_store_configuration(path: object, timeout_seconds: object) -> Path:
    """Validate shared public SQLite constructor arguments."""
    if not isinstance(path, Path):
        raise TypeError("path must be a Path")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise TypeError("timeout_seconds must be an int")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    return path


def _read_user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None or len(row) != 1 or not isinstance(row[0], int):
        raise SqlitePersistenceError("invalid SQLite schema version result")
    return row[0]


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _create_schema(connection: sqlite3.Connection) -> None:
    try:
        with connection:
            connection.execute(
                "CREATE TABLE catalog_entries ("
                "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
                "provider_id TEXT NOT NULL, "
                "external_id TEXT NOT NULL, "
                "url TEXT NOT NULL, "
                "first_seen_at TEXT NOT NULL, "
                "last_seen_at TEXT NOT NULL, "
                "UNIQUE(provider_id, external_id)"
                ")"
            )
            connection.execute(
                "CREATE TABLE observations ("
                "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
                "product_id TEXT NOT NULL, "
                "snapshot TEXT NOT NULL"
                ")"
            )
            connection.execute(
                "CREATE INDEX observations_product_sequence "
                "ON observations(product_id, sequence)"
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    except sqlite3.Error as error:
        raise SqlitePersistenceError("failed to initialize SQLite schema") from error


def _validate_schema(connection: sqlite3.Connection) -> None:
    tables = _user_tables(connection)
    if not {"catalog_entries", "observations"}.issubset(tables):
        raise SqlitePersistenceError("SQLite schema is missing required tables")
    if _table_columns(connection, "catalog_entries") != _CATALOG_COLUMNS:
        raise SqlitePersistenceError("catalog_entries schema is incompatible")
    if _table_columns(connection, "observations") != _OBSERVATION_COLUMNS:
        raise SqlitePersistenceError("observations schema is incompatible")


def _table_columns(
    connection: sqlite3.Connection,
    table: str,
) -> tuple[str, ...]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return tuple(row[1] for row in rows)


def _close_after_failed_open(connection: sqlite3.Connection) -> None:
    try:
        connection.close()
    except sqlite3.Error:
        return
