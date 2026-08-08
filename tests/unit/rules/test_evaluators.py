"""Unit tests for built-in independent rule evaluators."""

from dataclasses import replace
from decimal import Decimal
from unittest import TestCase

from core.domain import Currency, Money, Percentage, RuleType
from core.rules import RuleError
from core.rules.evaluators import BackInStockEvaluator, PriceDropEvaluator
from tests.unit.rules.helpers import TIMESTAMP, create_product, create_rule


class PriceDropEvaluatorTests(TestCase):
    """Verify price decrease behavior and optional thresholds."""

    def setUp(self) -> None:
        """Create the evaluator and its rule."""
        self.evaluator = PriceDropEvaluator()
        self.rule = create_rule(RuleType.PRICE_DROP)

    def test_exposes_supported_rule_type(self) -> None:
        self.assertIs(self.evaluator.rule_type, RuleType.PRICE_DROP)

    def test_supports_only_price_drop_rules(self) -> None:
        self.assertTrue(self.evaluator.supports(self.rule))
        self.assertFalse(
            self.evaluator.supports(create_rule(RuleType.BACK_IN_STOCK))
        )

    def test_matches_price_decrease(self) -> None:
        result = self.evaluator.evaluate(
            self.rule,
            create_product("100"),
            create_product("90"),
            TIMESTAMP,
        )

        self.assertTrue(result.matched)
        self.assertEqual(result.timestamp, TIMESTAMP)

    def test_does_not_match_without_previous_state(self) -> None:
        result = self.evaluator.evaluate(
            self.rule,
            None,
            create_product("90"),
            TIMESTAMP,
        )

        self.assertFalse(result.matched)
        self.assertIn("unavailable", result.reason)

    def test_does_not_compare_different_currencies(self) -> None:
        result = self.evaluator.evaluate(
            self.rule,
            create_product("100", currency=Currency.CZK),
            create_product("90", currency=Currency.EUR),
            TIMESTAMP,
        )

        self.assertFalse(result.matched)
        self.assertIn("currencies", result.reason)

    def test_does_not_match_equal_or_increased_price(self) -> None:
        for current_amount in ("100", "110"):
            with self.subTest(current_amount=current_amount):
                result = self.evaluator.evaluate(
                    self.rule,
                    create_product("100"),
                    create_product(current_amount),
                    TIMESTAMP,
                )
                self.assertFalse(result.matched)

    def test_prefers_current_original_price_over_previous_state(self) -> None:
        current = replace(
            create_product("80"),
            original_price=Money(Decimal("100"), Currency.CZK),
        )

        result = self.evaluator.evaluate(
            create_rule(
                RuleType.PRICE_DROP,
                parameters={"percentage": Decimal("20")},
            ),
            create_product("81"),
            current,
            TIMESTAMP,
        )

        self.assertTrue(result.matched)

    def test_available_only_rejects_unavailable_product(self) -> None:
        rule = create_rule(
            RuleType.PRICE_DROP,
            parameters={"available_only": True},
        )

        result = self.evaluator.evaluate(
            rule,
            create_product("100"),
            create_product("80", availability=False),
            TIMESTAMP,
        )

        self.assertFalse(result.matched)
        self.assertIn("unavailable", result.reason)

    def test_available_only_false_preserves_unavailable_matching(self) -> None:
        rule = create_rule(
            RuleType.PRICE_DROP,
            parameters={"available_only": False},
        )

        result = self.evaluator.evaluate(
            rule,
            create_product("100"),
            create_product("80", availability=False),
            TIMESTAMP,
        )

        self.assertTrue(result.matched)

    def test_rejects_invalid_available_only_parameter(self) -> None:
        rule = create_rule(
            RuleType.PRICE_DROP,
            parameters={"available_only": "yes"},
        )

        with self.assertRaisesRegex(RuleError, "available_only"):
            self.evaluator.evaluate(
                rule,
                create_product("100"),
                create_product("80"),
                TIMESTAMP,
            )

    def test_fixed_decimal_threshold_must_be_met(self) -> None:
        below = create_rule(
            RuleType.PRICE_DROP,
            parameters={"fixed_amount": Decimal("11")},
        )
        met = create_rule(
            RuleType.PRICE_DROP,
            parameters={"fixed_amount": Decimal("10")},
        )
        previous = create_product("100")
        current = create_product("90")

        self.assertFalse(
            self.evaluator.evaluate(below, previous, current, TIMESTAMP).matched
        )
        self.assertTrue(
            self.evaluator.evaluate(met, previous, current, TIMESTAMP).matched
        )

    def test_fixed_money_threshold_must_match_currency(self) -> None:
        matching = create_rule(
            RuleType.PRICE_DROP,
            parameters={"fixed_amount": Money(Decimal("10"), Currency.CZK)},
        )
        mismatched = create_rule(
            RuleType.PRICE_DROP,
            parameters={"fixed_amount": Money(Decimal("10"), Currency.EUR)},
        )
        previous = create_product("100")
        current = create_product("90")

        self.assertTrue(
            self.evaluator.evaluate(matching, previous, current, TIMESTAMP).matched
        )
        with self.assertRaisesRegex(RuleError, "currency must match"):
            self.evaluator.evaluate(mismatched, previous, current, TIMESTAMP)

    def test_rejects_invalid_fixed_threshold(self) -> None:
        for value in (Decimal("-1"), "10"):
            with self.subTest(value=value):
                rule = create_rule(
                    RuleType.PRICE_DROP,
                    parameters={"fixed_amount": value},
                )
                with self.assertRaisesRegex(RuleError, "fixed_amount"):
                    self.evaluator.evaluate(
                        rule,
                        create_product("100"),
                        create_product("90"),
                        TIMESTAMP,
                    )

    def test_percentage_decimal_threshold_must_be_met(self) -> None:
        below = create_rule(
            RuleType.PRICE_DROP,
            parameters={"percentage": Decimal("11")},
        )
        met = create_rule(
            RuleType.PRICE_DROP,
            parameters={"percentage": Decimal("10")},
        )
        previous = create_product("100")
        current = create_product("90")

        self.assertFalse(
            self.evaluator.evaluate(below, previous, current, TIMESTAMP).matched
        )
        self.assertTrue(
            self.evaluator.evaluate(met, previous, current, TIMESTAMP).matched
        )

    def test_accepts_percentage_value_object(self) -> None:
        rule = create_rule(
            RuleType.PRICE_DROP,
            parameters={"percentage": Percentage(Decimal("10"))},
        )

        result = self.evaluator.evaluate(
            rule,
            create_product("100"),
            create_product("90"),
            TIMESTAMP,
        )

        self.assertTrue(result.matched)

    def test_rejects_invalid_percentage_threshold(self) -> None:
        for value in (Decimal("-1"), Decimal("101"), "10"):
            with self.subTest(value=value):
                rule = create_rule(
                    RuleType.PRICE_DROP,
                    parameters={"percentage": value},
                )
                with self.assertRaisesRegex(RuleError, "percentage"):
                    self.evaluator.evaluate(
                        rule,
                        create_product("100"),
                        create_product("90"),
                        TIMESTAMP,
                    )


class BackInStockEvaluatorTests(TestCase):
    """Verify unavailable-to-available transition behavior."""

    def setUp(self) -> None:
        """Create the evaluator and its rule."""
        self.evaluator = BackInStockEvaluator()
        self.rule = create_rule(RuleType.BACK_IN_STOCK)

    def test_exposes_supported_rule_type(self) -> None:
        self.assertIs(self.evaluator.rule_type, RuleType.BACK_IN_STOCK)

    def test_supports_only_back_in_stock_rules(self) -> None:
        self.assertTrue(self.evaluator.supports(self.rule))
        self.assertFalse(
            self.evaluator.supports(create_rule(RuleType.PRICE_DROP))
        )

    def test_matches_unavailable_to_available_transition(self) -> None:
        result = self.evaluator.evaluate(
            self.rule,
            create_product("100", availability=False),
            create_product("100", availability=True),
            TIMESTAMP,
        )

        self.assertTrue(result.matched)
        self.assertEqual(result.timestamp, TIMESTAMP)

    def test_does_not_match_without_previous_state(self) -> None:
        result = self.evaluator.evaluate(
            self.rule,
            None,
            create_product("100", availability=True),
            TIMESTAMP,
        )

        self.assertFalse(result.matched)
        self.assertIn("unavailable", result.reason)

    def test_does_not_match_when_previously_available(self) -> None:
        result = self.evaluator.evaluate(
            self.rule,
            create_product("100", availability=True),
            create_product("100", availability=True),
            TIMESTAMP,
        )

        self.assertFalse(result.matched)
        self.assertIn("already available", result.reason)

    def test_does_not_match_when_product_remains_unavailable(self) -> None:
        result = self.evaluator.evaluate(
            self.rule,
            create_product("100", availability=False),
            create_product("100", availability=False),
            TIMESTAMP,
        )

        self.assertFalse(result.matched)
        self.assertIn("remains unavailable", result.reason)
