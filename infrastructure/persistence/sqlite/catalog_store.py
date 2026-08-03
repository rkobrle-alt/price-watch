"""SQLite implementation of durable product catalog membership."""

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from core.catalog import (
    CatalogEntry,
    CatalogStoreError,
    ProductReference,
)
from core.domain import ProviderId
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
    validate_store_configuration,
)


class SqliteCatalogStore:
    """Persist atomic catalog discoveries in a versioned SQLite database."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Validate configuration without opening or creating the database."""
        validated_path = validate_store_configuration(path, timeout_seconds)
        self._database = SqliteDatabase(validated_path, timeout_seconds)

    def record_discovery(
        self,
        references: tuple[ProductReference, ...],
        discovered_at: datetime,
    ) -> tuple[ProductReference, ...]:
        """Persist one discovery atomically and return new references."""
        _validate_discovery(references, discovered_at)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._database.open()
            new_references: list[ProductReference] = []
            with connection:
                for reference in references:
                    existing = connection.execute(
                        "SELECT last_seen_at FROM catalog_entries "
                        "WHERE provider_id = ? AND external_id = ?",
                        (str(reference.provider_id.value), reference.external_id),
                    ).fetchone()
                    if existing is None:
                        connection.execute(
                            "INSERT INTO catalog_entries ("
                            "provider_id, external_id, url, "
                            "first_seen_at, last_seen_at"
                            ") VALUES (?, ?, ?, ?, ?)",
                            (
                                str(reference.provider_id.value),
                                reference.external_id,
                                reference.url,
                                discovered_at.isoformat(),
                                discovered_at.isoformat(),
                            ),
                        )
                        new_references.append(reference)
                        continue
                    last_seen_at = _decode_datetime(existing[0], "last_seen_at")
                    if discovered_at < last_seen_at:
                        raise ValueError(
                            "discovered_at cannot precede an existing last_seen_at"
                        )
                    connection.execute(
                        "UPDATE catalog_entries SET url = ?, last_seen_at = ? "
                        "WHERE provider_id = ? AND external_id = ?",
                        (
                            reference.url,
                            discovered_at.isoformat(),
                            str(reference.provider_id.value),
                            reference.external_id,
                        ),
                    )
            return tuple(new_references)
        except _CatalogDataError as error:
            raise CatalogStoreError("invalid persisted catalog data") from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise CatalogStoreError("failed to record catalog discovery") from error
        finally:
            if connection is not None:
                _close_catalog_connection(self._database, connection)

    def list_entries(self, provider_id: ProviderId) -> tuple[CatalogEntry, ...]:
        """Return provider entries in stable first insertion order."""
        if not isinstance(provider_id, ProviderId):
            raise TypeError("provider_id must be a ProviderId")
        connection: sqlite3.Connection | None = None
        try:
            connection = self._database.open()
            rows = connection.execute(
                "SELECT provider_id, external_id, url, "
                "first_seen_at, last_seen_at FROM catalog_entries "
                "ORDER BY sequence"
            ).fetchall()
            entries = tuple(_decode_entry(row) for row in rows)
            return tuple(
                entry
                for entry in entries
                if entry.reference.provider_id == provider_id
            )
        except (_CatalogDataError, TypeError, ValueError) as error:
            raise CatalogStoreError("invalid persisted catalog data") from error
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise CatalogStoreError("failed to list catalog entries") from error
        finally:
            if connection is not None:
                _close_catalog_connection(self._database, connection)


class _CatalogDataError(ValueError):
    """Report invalid SQLite catalog row data."""


def _validate_discovery(
    references: object,
    discovered_at: object,
) -> None:
    if not isinstance(references, tuple) or not all(
        isinstance(reference, ProductReference) for reference in references
    ):
        raise TypeError("references must be a tuple of ProductReference values")
    identities = [
        (reference.provider_id, reference.external_id) for reference in references
    ]
    if len(set(identities)) != len(identities):
        raise ValueError("references must have unique provider and external IDs")
    if not isinstance(discovered_at, datetime):
        raise TypeError("discovered_at must be a datetime")
    if discovered_at.tzinfo is None or discovered_at.utcoffset() is None:
        raise ValueError("discovered_at must be timezone-aware")


def _decode_entry(row: tuple[object, ...]) -> CatalogEntry:
    provider_id = ProviderId(_decode_uuid(row[0], "provider_id"))
    try:
        reference = ProductReference(provider_id, row[1], row[2])
        return CatalogEntry(
            reference,
            _decode_datetime(row[3], "first_seen_at"),
            _decode_datetime(row[4], "last_seen_at"),
        )
    except (TypeError, ValueError) as error:
        raise _CatalogDataError("catalog row violates Core invariants") from error


def _decode_uuid(value: object, name: str) -> UUID:
    if not isinstance(value, str):
        raise _CatalogDataError(f"{name} must be a string UUID")
    try:
        identifier = UUID(value)
    except ValueError as error:
        raise _CatalogDataError(f"{name} must be a UUID") from error
    if str(identifier) != value:
        raise _CatalogDataError(f"{name} must be a canonical UUID")
    return identifier


def _decode_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise _CatalogDataError(f"{name} must be a string datetime")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise _CatalogDataError(f"{name} must be an ISO datetime") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise _CatalogDataError(f"{name} must be timezone-aware")
    return timestamp


def _close_catalog_connection(
    database: SqliteDatabase,
    connection: sqlite3.Connection,
) -> None:
    try:
        database.close(connection)
    except SqlitePersistenceError as error:
        raise CatalogStoreError("failed to close catalog database") from error
