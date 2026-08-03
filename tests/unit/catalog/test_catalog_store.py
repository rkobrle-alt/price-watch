"""Tests for durable catalog Core contracts."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from core.catalog import (
    CatalogEntry,
    CatalogStore,
    CatalogStoreError,
    ProductReference,
)
from core.domain import ProviderId

_NOW = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)


class _Store:
    def record_discovery(
        self,
        references: tuple[ProductReference, ...],
        discovered_at: datetime,
    ) -> tuple[ProductReference, ...]:
        return references

    def list_entries(self, provider_id: ProviderId) -> tuple[CatalogEntry, ...]:
        return ()


def _reference() -> ProductReference:
    return ProductReference(
        ProviderId(uuid4()),
        "p123",
        "https://lidl.cz/p/parkside-tool/p123",
    )


def _as_store(store: CatalogStore) -> CatalogStore:
    return store


def test_catalog_store_is_a_structural_protocol() -> None:
    store = _Store()

    assert _as_store(store) is store


def test_catalog_store_error_is_an_exception() -> None:
    assert issubclass(CatalogStoreError, Exception)


def test_catalog_entry_is_immutable_and_compares_by_value() -> None:
    reference = _reference()
    entry = CatalogEntry(reference, _NOW, _NOW + timedelta(hours=1))

    assert entry == CatalogEntry(reference, _NOW, _NOW + timedelta(hours=1))
    with pytest.raises(FrozenInstanceError):
        entry.reference = _reference()  # type: ignore[misc]


def test_catalog_entry_rejects_invalid_reference_type() -> None:
    with pytest.raises(TypeError, match="reference"):
        CatalogEntry(object(), _NOW, _NOW)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["first_seen_at", "last_seen_at"])
def test_catalog_entry_rejects_invalid_timestamp_type(field: str) -> None:
    arguments: dict[str, object] = {
        "reference": _reference(),
        "first_seen_at": _NOW,
        "last_seen_at": _NOW,
    }
    arguments[field] = "invalid"

    with pytest.raises(TypeError, match=field):
        CatalogEntry(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["first_seen_at", "last_seen_at"])
def test_catalog_entry_rejects_naive_timestamp(field: str) -> None:
    arguments = {
        "reference": _reference(),
        "first_seen_at": _NOW,
        "last_seen_at": _NOW,
    }
    arguments[field] = datetime(2026, 8, 3, 10, 0)

    with pytest.raises(ValueError, match=field):
        CatalogEntry(**arguments)


def test_catalog_entry_rejects_reversed_chronology() -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        CatalogEntry(_reference(), _NOW, _NOW - timedelta(seconds=1))
