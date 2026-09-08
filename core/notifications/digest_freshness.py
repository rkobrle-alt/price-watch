"""Deterministic freshness selection and product refresh boundary."""

from datetime import datetime, timedelta
from typing import Protocol

from core.domain import Percentage, Product
from core.notifications.daily_digest import DailyDiscountDigestEngine
from core.provider import ProviderError
from core.state import StateSnapshot


class DigestProductRefresher(Protocol):
    """Refresh selected products into the shared snapshot store."""

    def refresh(
        self, products: tuple[Product, ...], timestamp: datetime,
    ) -> tuple[ProviderError, ...]:
        """Persist successful observations and return reported provider errors."""
        ...


class DigestFreshnessPolicy:
    """Prioritize stale qualifying observations within a bounded budget."""

    def select(
        self,
        snapshots: tuple[StateSnapshot, ...],
        minimum_discount: Percentage,
        timestamp: datetime,
        limit: int = 200,
    ) -> tuple[Product, ...]:
        """Return oldest stale or future-dated qualifying products first."""
        if not isinstance(timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an int")
        if limit <= 0:
            raise ValueError("limit must be positive")
        digest = DailyDiscountDigestEngine().generate(
            snapshots, minimum_discount, timestamp.date(), timestamp,
        )
        identifiers = {product.id for product in digest.products}
        candidates = (
            snapshot for snapshot in snapshots
            if snapshot.product.id in identifiers
            and not timedelta(0) <= timestamp - snapshot.timestamp <= timedelta(hours=1)
        )
        ordered = sorted(
            candidates,
            key=lambda snapshot: (snapshot.timestamp, str(snapshot.product.id.value)),
        )
        return tuple(snapshot.product for snapshot in ordered[:limit])
