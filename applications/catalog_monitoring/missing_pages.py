"""Coordinate missing-page evidence using the deterministic Core policy."""

from datetime import datetime

from core.catalog import MissingPagePolicy, MissingProductPageStore
from core.domain import Product, ProviderId
from core.provider import ProviderError, ProviderProductNotFoundError
from core.state import LatestSnapshotReader, StateSnapshot


class ProductPageTracker:
    """Share durable missing-page outcomes between normal and digest refresh."""

    def __init__(self, store: MissingProductPageStore) -> None:
        """Retain an injected persistence boundary."""
        self.store = store

    def record(
        self, provider_id: ProviderId, products: tuple[Product, ...],
        errors: tuple[ProviderError, ...], timestamp: datetime,
    ) -> None:
        """Clear successful resources and advance only typed missing failures."""
        pages = {(p.provider_id, p.url): p for p in self.store.load()}
        for product in products:
            pages.pop((product.provider_id, product.url), None)
        for error in errors:
            if isinstance(error, ProviderProductNotFoundError):
                key = (provider_id, error.url)
                pages[key] = MissingPagePolicy().record(provider_id, error.url, timestamp, pages.get(key))
        self.store.save(tuple(pages.values()))


class PageAwareSnapshotReader:
    """Exclude known missing URLs without mutating historical observations."""

    def __init__(self, reader: LatestSnapshotReader, store: MissingProductPageStore) -> None:
        """Retain explicit observation and lifecycle readers."""
        self._reader = reader
        self._store = store

    def latest_snapshots(self) -> tuple[StateSnapshot, ...]:
        """Return latest observations for resources not currently missing."""
        pages = {(p.provider_id, p.url) for p in self._store.load()}
        return tuple(s for s in self._reader.latest_snapshots() if (s.product.provider_id, s.product.url) not in pages)
