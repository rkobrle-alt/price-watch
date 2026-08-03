"""Structural contract for durable product catalog membership."""

from datetime import datetime
from typing import Protocol

from core.catalog.entry import CatalogEntry
from core.catalog.reference import ProductReference
from core.domain import ProviderId


class CatalogStore(Protocol):
    """Persist catalog discoveries independently of provider transport."""

    def record_discovery(
        self,
        references: tuple[ProductReference, ...],
        discovered_at: datetime,
    ) -> tuple[ProductReference, ...]:
        """Persist one atomic discovery and return newly inserted references."""
        ...

    def list_entries(self, provider_id: ProviderId) -> tuple[CatalogEntry, ...]:
        """Return retained entries for a provider in stable insertion order."""
        ...
