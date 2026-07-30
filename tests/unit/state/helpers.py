"""Typed factories for State Store tests."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from core.domain import (
    Currency,
    Money,
    Percentage,
    Product,
    ProductId,
    ProviderId,
)

TIMESTAMP = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def create_product(
    *,
    product_id: ProductId | None = None,
    amount: str = "99.90",
) -> Product:
    """Create a valid product with selected identity and price."""
    return Product(
        id=ProductId(uuid4()) if product_id is None else product_id,
        provider_id=ProviderId(uuid4()),
        brand="Example",
        name="Coffee",
        current_price=Money(Decimal(amount), Currency.CZK),
        original_price=None,
        discount_percent=Percentage(Decimal("0")),
        url="https://example.test/product",
        image_url=None,
        created_at=TIMESTAMP,
    )
