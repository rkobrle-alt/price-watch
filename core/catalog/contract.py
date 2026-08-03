"""Structural contract for product catalog discovery."""

from typing import Protocol

from core.catalog.reference import ProductReference


class ProductCatalog(Protocol):
    """Discover immutable product references from a provider catalog."""

    def discover(self) -> tuple[ProductReference, ...]:
        """Return the currently discoverable product references."""
        ...
