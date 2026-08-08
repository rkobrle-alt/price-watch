"""Deterministic reference-price enrichment for price evaluation."""

from dataclasses import replace
from decimal import Decimal

from core.domain import Percentage, Product
from core.state import StateSnapshot


class PriceReferencePolicy:
    """Enrich a product with its approved deterministic reference price."""

    def enrich(
        self,
        current: Product,
        history: tuple[StateSnapshot, ...],
    ) -> Product:
        """Return a product carrying provider or historical reference data."""
        if not isinstance(current, Product):
            raise TypeError("current must be a Product")
        if not isinstance(history, tuple) or not all(
            isinstance(snapshot, StateSnapshot) for snapshot in history
        ):
            raise TypeError("history must be a tuple of StateSnapshot values")
        if any(snapshot.product.id != current.id for snapshot in history):
            raise ValueError("history snapshots must belong to the current product")

        reference = current.original_price
        if reference is None:
            prices = (
                snapshot.product.current_price
                for snapshot in history
                if snapshot.product.currency is current.currency
            )
            reference = max(prices, key=lambda money: money.amount, default=None)
        if reference is None:
            return current

        discount = _discount_percentage(
            reference.amount,
            current.current_price.amount,
        )
        return replace(
            current,
            original_price=reference,
            discount_percent=Percentage(discount),
        )


def _discount_percentage(reference: Decimal, current: Decimal) -> Decimal:
    if reference == Decimal("0") or current >= reference:
        return Decimal("0")
    return (reference - current) * Decimal("100") / reference
