"""Unit tests for domain value objects."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from core.domain import Currency, Money, Percentage, ProductId, ProviderId
from core.domain.exceptions import ValidationError


class MoneyTests(TestCase):
    """Verify Money invariants."""

    def test_accepts_non_negative_decimal_amount(self) -> None:
        money = Money(amount=Decimal("12.50"), currency=Currency.CZK)

        self.assertEqual(money.amount, Decimal("12.50"))
        self.assertEqual(money.currency, Currency.CZK)
        with self.assertRaises(FrozenInstanceError):
            money.amount = Decimal("1")  # type: ignore[misc]

    def test_rejects_non_decimal_amount(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a Decimal"):
            Money(amount=1.5, currency=Currency.EUR)  # type: ignore[arg-type]

    def test_rejects_non_finite_amount(self) -> None:
        for amount in (Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(ValidationError, "must be finite"):
                    Money(amount=amount, currency=Currency.USD)

    def test_rejects_negative_amount(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot be negative"):
            Money(amount=Decimal("-0.01"), currency=Currency.PLN)

    def test_rejects_invalid_currency(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a Currency"):
            Money(amount=Decimal("1"), currency="CZK")  # type: ignore[arg-type]


class PercentageTests(TestCase):
    """Verify Percentage invariants."""

    def test_accepts_inclusive_boundaries(self) -> None:
        self.assertEqual(Percentage(Decimal("0")).value, Decimal("0"))
        self.assertEqual(Percentage(Decimal("100")).value, Decimal("100"))

    def test_rejects_non_decimal_value(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a Decimal"):
            Percentage(50)  # type: ignore[arg-type]

    def test_rejects_non_finite_value(self) -> None:
        for value in (Decimal("NaN"), Decimal("-Infinity")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "must be finite"):
                    Percentage(value)

    def test_rejects_values_outside_range(self) -> None:
        for value in (Decimal("-0.01"), Decimal("100.01")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "between 0 and 100"):
                    Percentage(value)


class IdentifierTests(TestCase):
    """Verify UUID-backed identifier invariants."""

    def test_wraps_uuid_values(self) -> None:
        value = uuid4()
        self.assertEqual(ProductId(value).value, value)
        self.assertEqual(ProviderId(value).value, value)

    def test_rejects_non_uuid_values(self) -> None:
        with self.assertRaisesRegex(ValidationError, "product id"):
            ProductId("id")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValidationError, "provider id"):
            ProviderId("id")  # type: ignore[arg-type]
