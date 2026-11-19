"""Transactional missing-page lifecycle evidence in the catalog database."""

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from core.catalog import CatalogStoreError, MissingProductPage
from core.domain import ProviderId
from infrastructure.persistence.sqlite.database import SqliteDatabase, SqlitePersistenceError, validate_store_configuration


class SqliteMissingProductPageStore:
    """Persist missing resources while preserving prices and reservations."""

    def __init__(self, path: Path, timeout_seconds: int = 5) -> None:
        """Configure the shared catalog database."""
        self._database = SqliteDatabase(validate_store_configuration(path, timeout_seconds), timeout_seconds)

    def load(self) -> tuple[MissingProductPage, ...]:
        """Read missing-page evidence in deterministic provider/URL order."""
        connection = None
        try:
            connection = self._database.open()
            rows = connection.execute(
                "SELECT provider_id, url, failures, checked_at, retry_at "
                "FROM missing_product_pages ORDER BY provider_id, url"
            ).fetchall()
            return tuple(MissingProductPage(
                ProviderId(UUID(row[0])), row[1], row[2],
                datetime.fromisoformat(row[3]), datetime.fromisoformat(row[4]),
            ) for row in rows)
        except (sqlite3.Error, SqlitePersistenceError, TypeError, ValueError, AttributeError) as error:
            raise CatalogStoreError("failed to read missing-page evidence") from error
        finally:
            self._close(connection)

    def save(self, pages: tuple[MissingProductPage, ...]) -> None:
        """Replace the small evidence set in one atomic transaction."""
        if not isinstance(pages, tuple) or not all(isinstance(page, MissingProductPage) for page in pages):
            raise TypeError("pages must be a tuple of MissingProductPage")
        keys = {(page.provider_id, page.url) for page in pages}
        if len(keys) != len(pages):
            raise ValueError("pages must have unique identities")
        connection = None
        try:
            connection = self._database.open()
            with connection:
                connection.execute("DELETE FROM missing_product_pages")
                connection.executemany(
                    "INSERT INTO missing_product_pages VALUES (?, ?, ?, ?, ?)",
                    [(str(p.provider_id.value), p.url, p.failures, p.checked_at.isoformat(), p.retry_at.isoformat()) for p in pages],
                )
        except (sqlite3.Error, SqlitePersistenceError) as error:
            raise CatalogStoreError("failed to save missing-page evidence") from error
        finally:
            self._close(connection)

    def _close(self, connection: sqlite3.Connection | None) -> None:
        if connection is not None:
            try:
                self._database.close(connection)
            except SqlitePersistenceError as error:
                raise CatalogStoreError("failed to close missing-page database") from error
