"""Unit tests for the domain public API, enums, and exceptions."""

from unittest import TestCase

import core.domain as domain
from core.domain import Currency, DomainError, ProviderStatus, RuleType, ValidationError


class EnumTests(TestCase):
    """Verify the specified enum contracts."""

    def test_currency_members(self) -> None:
        self.assertEqual(
            list(Currency),
            [Currency.CZK, Currency.EUR, Currency.USD, Currency.PLN],
        )
        self.assertEqual(Currency.CZK.value, "CZK")

    def test_provider_status_members(self) -> None:
        self.assertEqual(
            list(ProviderStatus),
            [
                ProviderStatus.ACTIVE,
                ProviderStatus.DISABLED,
                ProviderStatus.MAINTENANCE,
            ],
        )

    def test_rule_type_members(self) -> None:
        self.assertEqual(
            list(RuleType),
            [RuleType.PRICE_DROP, RuleType.BACK_IN_STOCK],
        )


class ExceptionTests(TestCase):
    """Verify the domain exception hierarchy."""

    def test_validation_error_is_domain_error(self) -> None:
        self.assertIsInstance(ValidationError("invalid"), DomainError)


class PublicApiTests(TestCase):
    """Verify all documented domain objects are exported."""

    def test_public_exports(self) -> None:
        expected = {
            "Currency", "DomainError", "Money", "Notification", "Percentage",
            "PriceRecord", "Product", "ProductId", "Provider", "ProviderId",
            "ProviderStatus", "Rule", "RuleType", "ValidationError",
        }

        self.assertEqual(set(domain.__all__), expected)
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue(getattr(domain, name).__doc__)
