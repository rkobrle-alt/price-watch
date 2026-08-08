"""Private versioned SQLite database lifecycle for durable stores."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 3

_CATALOG_COLUMNS_V1 = (
    "sequence",
    "provider_id",
    "external_id",
    "url",
    "first_seen_at",
    "last_seen_at",
)
_CATALOG_COLUMNS = _CATALOG_COLUMNS_V1 + ("last_refresh_attempt_at",)
_OBSERVATION_COLUMNS = ("sequence", "product_id", "snapshot")
_RESERVATION_COLUMNS = (
    "product_id",
    "rule_type",
    "currency",
    "price_amount",
    "reserved_at",
)
_LEGACY_TABLES = {"catalog_entries", "observations"}
_REQUIRED_TABLES = _LEGACY_TABLES | {"notification_reservations"}


class SqlitePersistenceError(Exception):
    """Report an internal SQLite lifecycle or schema failure."""


class SqliteDatabase:
    """Open, initialize, migrate, validate and close one Price Watch database."""

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
        elif version == 1:
            _validate_schema_columns(
                connection,
                _CATALOG_COLUMNS_V1,
                _LEGACY_TABLES,
                False,
            )
            _migrate_version_one(connection)
            _validate_schema_columns(
                connection,
                _CATALOG_COLUMNS,
                _LEGACY_TABLES,
                False,
            )
            _migrate_version_two(connection)
        elif version == 2:
            _validate_schema_columns(
                connection,
                _CATALOG_COLUMNS,
                _LEGACY_TABLES,
                False,
            )
            _migrate_version_two(connection)
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
                "last_refresh_attempt_at TEXT, "
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
            _create_refresh_index(connection)
            _create_reservation_table(connection)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    except sqlite3.Error as error:
        raise SqlitePersistenceError("failed to initialize SQLite schema") from error


def _migrate_version_one(connection: sqlite3.Connection) -> None:
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "ALTER TABLE catalog_entries "
                "ADD COLUMN last_refresh_attempt_at TEXT"
            )
            _create_refresh_index(connection)
            connection.execute("PRAGMA user_version = 2")
    except sqlite3.Error as error:
        raise SqlitePersistenceError("failed to migrate SQLite schema") from error


def _migrate_version_two(connection: sqlite3.Connection) -> None:
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            _create_reservation_table(connection)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    except sqlite3.Error as error:
        raise SqlitePersistenceError("failed to migrate SQLite schema") from error


def _create_refresh_index(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE INDEX catalog_refresh_order ON catalog_entries("
        "provider_id, last_refresh_attempt_at, sequence"
        ")"
    )


def _create_reservation_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE notification_reservations ("
        "product_id TEXT NOT NULL, "
        "rule_type TEXT NOT NULL, "
        "currency TEXT NOT NULL, "
        "price_amount TEXT NOT NULL, "
        "reserved_at TEXT NOT NULL, "
        "PRIMARY KEY(product_id, rule_type, currency, price_amount)"
        ")"
    )


def _validate_schema(connection: sqlite3.Connection) -> None:
    _validate_schema_columns(
        connection,
        _CATALOG_COLUMNS,
        _REQUIRED_TABLES,
        True,
    )


def _validate_schema_columns(
    connection: sqlite3.Connection,
    catalog_columns: tuple[str, ...],
    required_tables: set[str],
    validate_reservations: bool,
) -> None:
    tables = _user_tables(connection)
    if not required_tables.issubset(tables):
        raise SqlitePersistenceError("SQLite schema is missing required tables")
    if _table_columns(connection, "catalog_entries") != catalog_columns:
        raise SqlitePersistenceError("catalog_entries schema is incompatible")
    if _table_columns(connection, "observations") != _OBSERVATION_COLUMNS:
        raise SqlitePersistenceError("observations schema is incompatible")
    if validate_reservations and (
        _table_columns(connection, "notification_reservations")
        != _RESERVATION_COLUMNS
    ):
        raise SqlitePersistenceError(
            "notification_reservations schema is incompatible"
        )


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
