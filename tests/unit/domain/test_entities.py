"""Unit tests for domain entities."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from core.domain import (
    Currency,
    Money,
    Notification,
    Percentage,
    PriceRecord,
    Product,
    ProductId,
    Provider,
    ProviderId,
    Rule,
    ValidationError,
)


class DomainEntityTestCase(TestCase):
    """Provide typed factories for entity tests."""

    def setUp(self) -> None:
        """Create identifiers and an aware timestamp."""
        self.product_id = ProductId(uuid4())
        self.provider_id = ProviderId(uuid4())
        self.timestamp = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)

    def create_product(
        self,
        *,
        name: str = "Coffee",
        original_price: Money | None = None,
        created_at: datetime | object | None = None,
    ) -> Product:
        """Create a product with valid defaults and selected overrides."""
        timestamp = self.timestamp if created_at is None else created_at
        return Product(
            id=self.product_id,
            provider_id=self.provider_id,
            brand="Example",
            name=name,
            current_price=Money(Decimal("99.90"), Currency.CZK),
            original_price=original_price,
            discount_percent=Percentage(Decimal("10")),
            url="https://example.test/product",
            image_url=None,
            created_at=timestamp,  # type: ignore[arg-type]
        )


class ProductTests(DomainEntityTestCase):
    """Verify Product behavior and validation."""

    def test_creates_immutable_product_with_derived_currency(self) -> None:
        product = self.create_product(
            original_price=Money(Decimal("110"), Currency.CZK)
        )

        self.assertEqual(product.name, "Coffee")
        self.assertEqual(product.currency, Currency.CZK)
        self.assertIsNone(product.image_url)
        with self.assertRaises(FrozenInstanceError):
            product.name = "Tea"  # type: ignore[misc]

    def test_allows_missing_original_price(self) -> None:
        self.assertIsNone(self.create_product().original_price)

    def test_rejects_blank_name(self) -> None:
        for name in ("", " \t"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValidationError, "cannot be empty"):
                    self.create_product(name=name)

    def test_rejects_non_string_name(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot be empty"):
            self.create_product(name=1)  # type: ignore[arg-type]

    def test_rejects_invalid_original_price_type(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Money or None"):
            self.create_product(original_price="100")  # type: ignore[arg-type]

    def test_rejects_mixed_price_currencies(self) -> None:
        with self.assertRaisesRegex(ValidationError, "same currency"):
            self.create_product(
                original_price=Money(Decimal("110"), Currency.EUR)
            )

    def test_rejects_non_datetime_created_at(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a datetime"):
            self.create_product(created_at="today")

    def test_rejects_naive_created_at(self) -> None:
        with self.assertRaisesRegex(ValidationError, "timezone-aware"):
            self.create_product(created_at=datetime(2026, 7, 29))


class ProviderTests(DomainEntityTestCase):
    """Verify Provider behavior and validation."""

    def test_creates_provider(self) -> None:
        provider = Provider(
            id=self.provider_id,
            name="Shop",
            country="CZ",
            website="https://example.test",
        )

        self.assertEqual(provider.country, "CZ")

    def test_rejects_blank_name(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot be empty"):
            Provider(
                id=self.provider_id,
                name="  ",
                country="CZ",
                website="https://example.test",
            )


class PriceRecordTests(DomainEntityTestCase):
    """Verify PriceRecord behavior and validation."""

    def create_record(
        self,
        price: Decimal | object = Decimal("10"),
        currency: Currency | object = Currency.EUR,
        captured_at: datetime | object | None = None,
    ) -> PriceRecord:
        """Create a price record with valid defaults and selected overrides."""
        timestamp = self.timestamp if captured_at is None else captured_at
        return PriceRecord(
            product_id=self.product_id,
            price=price,  # type: ignore[arg-type]
            currency=currency,  # type: ignore[arg-type]
            captured_at=timestamp,  # type: ignore[arg-type]
        )

    def test_creates_price_record(self) -> None:
        record = self.create_record()
        self.assertEqual(record.price, Decimal("10"))

    def test_rejects_non_decimal_price(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a Decimal"):
            self.create_record(price=10.0)

    def test_rejects_non_finite_price(self) -> None:
        for price in (Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(price=price):
                with self.assertRaisesRegex(ValidationError, "must be finite"):
                    self.create_record(price=price)

    def test_rejects_negative_price(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot be negative"):
            self.create_record(price=Decimal("-1"))

    def test_rejects_invalid_currency(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a Currency"):
            self.create_record(currency="EUR")

    def test_rejects_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(ValidationError, "timezone-aware"):
            self.create_record(captured_at=datetime(2026, 7, 29))


class RuleTests(DomainEntityTestCase):
    """Verify Rule behavior and validation."""

    def test_creates_rule(self) -> None:
        self.assertTrue(Rule(uuid4(), "Price dropped", True).enabled)

    def test_rejects_non_uuid_id(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a UUID"):
            Rule("id", "Price dropped", True)  # type: ignore[arg-type]

    def test_rejects_blank_name(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot be empty"):
            Rule(uuid4(), " ", True)

    def test_rejects_non_boolean_enabled(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a bool"):
            Rule(uuid4(), "Price dropped", 1)  # type: ignore[arg-type]


class NotificationTests(DomainEntityTestCase):
    """Verify Notification behavior and validation."""

    def test_creates_notification(self) -> None:
        notification = Notification(
            uuid4(), self.product_id, "Price changed", self.timestamp
        )
        self.assertEqual(notification.message, "Price changed")

    def test_rejects_non_uuid_id(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a UUID"):
            Notification(
                "id",  # type: ignore[arg-type]
                self.product_id,
                "Price changed",
                self.timestamp,
            )

    def test_rejects_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(ValidationError, "timezone-aware"):
            Notification(
                uuid4(), self.product_id, "Price changed", datetime(2026, 7, 29)
            )
