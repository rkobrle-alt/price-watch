"""Structural contract for reading durable product observations."""

from typing import Protocol

from core.domain import ProductId
from core.state.snapshot import StateSnapshot


class ObservationHistory(Protocol):
    """Read chronologically ordered observations for one product."""

    def history(
        self,
        product_id: ProductId,
        limit: int | None = None,
    ) -> tuple[StateSnapshot, ...]:
        """Return all or the most recent bounded product observations."""
        ...
