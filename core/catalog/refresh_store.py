"""Structural contract for durable catalog refresh ordering."""

from datetime import datetime
from typing import Protocol

from core.catalog.reference import ProductReference
from core.domain import ProviderId


class CatalogRefreshStore(Protocol):
    """Select bounded refresh batches and persist completed attempts."""

    def list_refresh_batch(
        self,
        provider_id: ProviderId,
        limit: int,
    ) -> tuple[ProductReference, ...]:
        """Return the next never-refreshed or oldest-refreshed references."""
        ...

    def record_refresh_attempt(
        self,
        references: tuple[ProductReference, ...],
        attempted_at: datetime,
    ) -> None:
        """Record one atomic refresh attempt for retained references."""
        ...
