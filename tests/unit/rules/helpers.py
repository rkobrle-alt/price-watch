"""Typed test factories for Rule Engine unit tests."""

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
    Rule,
    RuleType,
)

TIMESTAMP = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)


def create_product(
    amount: str,
    *,
    currency: Currency = Currency.CZK,
    availability: bool = True,
) -> Product:
    """Create a product state with selected price and availability."""
    return Product(
        id=ProductId(uuid4()),
        provider_id=ProviderId(uuid4()),
        brand="Example",
        name="Coffee",
        current_price=Money(Decimal(amount), currency),
        original_price=None,
        discount_percent=Percentage(Decimal("0")),
        url="https://example.test/product",
        image_url=None,
        created_at=TIMESTAMP,
        availability=availability,
    )


def create_rule(
    rule_type: RuleType,
    *,
    enabled: bool = True,
    parameters: dict[str, object] | None = None,
) -> Rule:
    """Create a rule with selected classification and parameters."""
    return Rule(
        id=uuid4(),
        name="Test rule",
        enabled=enabled,
        rule_type=rule_type,
        parameters={} if parameters is None else parameters,
    )
