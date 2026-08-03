"""Tests for the durable catalog refresh-order contract."""

from datetime import datetime

from core.catalog import CatalogRefreshStore, ProductReference
from core.domain import ProviderId


class _RefreshStore:
    def list_refresh_batch(
        self,
        provider_id: ProviderId,
        limit: int,
    ) -> tuple[ProductReference, ...]:
        return ()

    def record_refresh_attempt(
        self,
        references: tuple[ProductReference, ...],
        attempted_at: datetime,
    ) -> None:
        return None


def _as_refresh_store(store: CatalogRefreshStore) -> CatalogRefreshStore:
    return store


def test_catalog_refresh_store_is_a_structural_protocol() -> None:
    store = _RefreshStore()

    assert _as_refresh_store(store) is store
