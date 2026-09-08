"""Private bounded adapter reusing the Lidl synchronization composition."""

from datetime import datetime

from applications.catalog_monitoring import CatalogBatchSynchronizer
from core.catalog import ProductReference
from core.domain import Product
from core.provider import ProviderError


class _LidlDigestRefresher:
    """Recheck product URLs without rules or catalog-rotation mutations."""

    def __init__(self, synchronizer: CatalogBatchSynchronizer) -> None:
        self._synchronizer = synchronizer

    def refresh(
        self, products: tuple[Product, ...], timestamp: datetime,
    ) -> tuple[ProviderError, ...]:
        """Persist successful rechecks in batches and retain provider failures."""
        errors: list[ProviderError] = []
        for offset in range(0, len(products), 25):
            references = tuple(
                ProductReference(product.provider_id, product.url, product.url)
                for product in products[offset:offset + 25]
            )
            result = self._synchronizer.synchronize(references, (), timestamp)
            errors.extend(result.provider_errors)
        return tuple(errors)
