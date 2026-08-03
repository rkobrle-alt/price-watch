"""Application boundary for synchronizing one catalog reference batch."""

from datetime import datetime
from typing import Protocol

from applications.synchronization import SynchronizationResult
from core.catalog import ProductReference
from core.domain import Rule


class CatalogBatchSynchronizer(Protocol):
    """Synchronize one selected product-reference batch."""

    def synchronize(
        self,
        references: tuple[ProductReference, ...],
        rules: tuple[Rule, ...],
        timestamp: datetime,
    ) -> SynchronizationResult:
        """Run the existing product synchronization behavior for a batch."""
        ...
