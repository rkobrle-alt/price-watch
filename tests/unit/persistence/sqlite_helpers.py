"""Deterministic helpers for SQLite persistence tests."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from core.catalog import ProductReference
from core.domain import ProviderId

CATALOG_PROVIDER_ID = ProviderId(
    UUID("018f0000-0000-7000-8000-000000000020")
)
OTHER_PROVIDER_ID = ProviderId(
    UUID("018f0000-0000-7000-8000-000000000021")
)


def create_reference(
    external_id: str,
    *,
    provider_id: ProviderId = CATALOG_PROVIDER_ID,
    suffix: str = "tool",
) -> ProductReference:
    """Create one deterministic Lidl-shaped catalog reference."""
    return ProductReference(
        provider_id,
        external_id,
        f"https://lidl.cz/p/parkside-{suffix}/{external_id}",
    )


@contextmanager
def open_database(path: Path) -> Iterator[sqlite3.Connection]:
    """Open and close a test database used for direct corruption setup."""
    connection = sqlite3.connect(path)
    try:
        yield connection
    finally:
        connection.close()