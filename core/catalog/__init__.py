"""Public API for provider-neutral product catalog discovery."""

from core.catalog.contract import ProductCatalog
from core.catalog.exceptions import CatalogError
from core.catalog.reference import ProductReference

__all__ = ["CatalogError", "ProductCatalog", "ProductReference"]
