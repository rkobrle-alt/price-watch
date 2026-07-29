"""Unit tests for the ADR-0004 domain extensions."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

import core.domain as domain
from core.domain import (
    Currency,
    Money,
    Percentage,
    Product,
    ProductId,
    ProviderId,
    Rule,
    RuleType,
    ValidationError,
)


def create_product(*, availability: bool = True) -> Product:
    """Create a valid product with a selected availability state."""
    return Product(
        id=ProductId(uuid4()),
        provider_id=ProviderId(uuid4()),
        brand="Example",
        name="Coffee",
        current_price=Money(Decimal("99.90"), Currency.CZK),
        original_price=None,
        discount_percent=Percentage(Decimal("0")),
        url="https://example.test/product",
        image_url=None,
        created_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
        availability=availability,
    )


class RuleDomainExtensionTests(TestCase):
    """Verify rule classification and immutable opaque parameters."""

    def test_existing_constructor_receives_compatible_rule_type(self) -> None:
        rule = Rule(uuid4(), "Price dropped", True)

        self.assertIs(rule.rule_type, RuleType.PRICE_DROP)
        self.assertEqual(dict(rule.parameters), {})

    def test_accepts_explicit_rule_type_and_parameters(self) -> None:
        rule = Rule(
            id=uuid4(),
            name="Back in stock",
            enabled=True,
            rule_type=RuleType.BACK_IN_STOCK,
            parameters={"notify_once": True},
        )

        self.assertIs(rule.rule_type, RuleType.BACK_IN_STOCK)
        self.assertEqual(rule.parameters, {"notify_once": True})

    def test_rejects_missing_rule_type(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a RuleType"):
            Rule(
                id=uuid4(),
                name="Invalid",
                enabled=True,
                rule_type=None,  # type: ignore[arg-type]
            )

    def test_rejects_non_mapping_parameters(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a mapping"):
            Rule(
                id=uuid4(),
                name="Invalid",
                enabled=True,
                parameters=[],  # type: ignore[arg-type]
            )

    def test_parameters_are_copied_and_immutable(self) -> None:
        source = {"percentage": Decimal("10")}
        rule = Rule(
            id=uuid4(),
            name="Price dropped",
            enabled=True,
            parameters=source,
        )

        source["percentage"] = Decimal("20")

        self.assertEqual(rule.parameters["percentage"], Decimal("10"))
        with self.assertRaises(TypeError):
            rule.parameters["percentage"] = Decimal("30")  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            rule.parameters = {}  # type: ignore[misc]

    def test_default_parameter_mappings_are_not_shared(self) -> None:
        first = Rule(uuid4(), "First", True)
        second = Rule(uuid4(), "Second", True)

        self.assertIsNot(first.parameters, second.parameters)


class ProductDomainExtensionTests(TestCase):
    """Verify product availability state and compatibility."""

    def test_availability_defaults_to_true(self) -> None:
        product = create_product()

        self.assertTrue(product.availability)

    def test_accepts_unavailable_product_and_remains_immutable(self) -> None:
        product = create_product(availability=False)

        self.assertFalse(product.availability)
        with self.assertRaises(FrozenInstanceError):
            product.availability = True  # type: ignore[misc]

    def test_rejects_non_boolean_availability(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a bool"):
            create_product(availability=1)  # type: ignore[arg-type]


class DomainExtensionPublicApiTests(TestCase):
    """Verify extended objects remain available through the Domain API."""

    def test_rule_product_and_rule_type_remain_exported(self) -> None:
        self.assertIs(domain.Rule, Rule)
        self.assertIs(domain.Product, Product)
        self.assertIs(domain.RuleType, RuleType)
