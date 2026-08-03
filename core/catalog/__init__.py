"""Public API for provider-neutral product catalog discovery."""

from core.catalog.contract import ProductCatalog
from core.catalog.entry import CatalogEntry
from core.catalog.exceptions import CatalogError, CatalogStoreError
from core.catalog.reference import ProductReference
from core.catalog.refresh_store import CatalogRefreshStore
from core.catalog.store import CatalogStore

__all__ = [
    "CatalogEntry",
    "CatalogError",
    "CatalogRefreshStore",
    "CatalogStore",
    "CatalogStoreError",
    "ProductCatalog",
    "ProductReference",
]