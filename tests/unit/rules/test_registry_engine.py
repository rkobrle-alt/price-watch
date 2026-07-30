"""Unit tests for evaluator registration and engine coordination."""

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase

from core.domain import Product, Rule, RuleType
from core.rules import (
    EvaluationResult,
    EvaluatorRegistry,
    RuleEngine,
    RuleError,
    RuleEvaluator,
)
from core.rules.evaluators import BackInStockEvaluator, PriceDropEvaluator
from tests.unit.rules.helpers import TIMESTAMP, create_product, create_rule


@dataclass(slots=True)
class RecordingEvaluator:
    """Record calls while satisfying the RuleEvaluator protocol."""

    rule_type: RuleType
    result: EvaluationResult
    calls: int = 0

    def supports(self, rule: Rule) -> bool:
        """Return whether the evaluator handles the rule type."""
        return rule.rule_type is self.rule_type

    def evaluate(
        self,
        rule: Rule,
        previous: Product | None,
        current: Product,
        timestamp: datetime,
    ) -> EvaluationResult:
        """Record delegation and return a predefined result."""
        self.calls += 1
        return self.result


class EvaluatorRegistryTests(TestCase):
    """Verify evaluator registry lifecycle and validation."""

    def setUp(self) -> None:
        """Create an empty registry and built-in evaluators."""
        self.registry = EvaluatorRegistry()
        self.price_drop: RuleEvaluator = PriceDropEvaluator()
        self.back_in_stock: RuleEvaluator = BackInStockEvaluator()

    def test_register_get_list_and_unregister(self) -> None:
        self.registry.register(self.price_drop)
        self.registry.register(self.back_in_stock)

        self.assertIs(self.registry.get(RuleType.PRICE_DROP), self.price_drop)
        self.assertEqual(
            self.registry.list(),
            (self.price_drop, self.back_in_stock),
        )
        self.assertIs(
            self.registry.unregister(RuleType.PRICE_DROP),
            self.price_drop,
        )
        self.assertEqual(self.registry.list(), (self.back_in_stock,))

    def test_duplicate_registration_raises_rule_error(self) -> None:
        self.registry.register(self.price_drop)

        with self.assertRaisesRegex(RuleError, "already registered"):
            self.registry.register(PriceDropEvaluator())

    def test_unknown_rule_type_raises_for_get_and_unregister(self) -> None:
        for operation in (self.registry.get, self.registry.unregister):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(RuleError, "no evaluator registered"):
                    operation(RuleType.BACK_IN_STOCK)

    def test_missing_evaluator_members_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuleError, "invalid evaluator") as context:
            self.registry.register(SimpleNamespace())  # type: ignore[arg-type]
        self.assertIsInstance(context.exception.__cause__, AttributeError)

    def test_invalid_rule_type_is_rejected(self) -> None:
        invalid = SimpleNamespace(
            rule_type="PRICE_DROP",
            supports=lambda rule: True,
            evaluate=lambda: None,
        )

        with self.assertRaisesRegex(RuleError, "invalid evaluator"):
            self.registry.register(invalid)  # type: ignore[arg-type]

    def test_non_callable_evaluate_is_rejected(self) -> None:
        invalid = SimpleNamespace(
            rule_type=RuleType.PRICE_DROP,
            supports=lambda rule: True,
            evaluate=None,
        )

        with self.assertRaisesRegex(RuleError, "invalid evaluator"):
            self.registry.register(invalid)  # type: ignore[arg-type]

    def test_non_callable_supports_is_rejected(self) -> None:
        invalid = SimpleNamespace(
            rule_type=RuleType.PRICE_DROP,
            supports=None,
            evaluate=lambda: None,
        )

        with self.assertRaisesRegex(RuleError, "invalid evaluator"):
            self.registry.register(invalid)  # type: ignore[arg-type]


class RuleEngineTests(TestCase):
    """Verify the engine coordinates without containing evaluator logic."""

    def setUp(self) -> None:
        """Create product states used for delegation tests."""
        self.previous = create_product("100")
        self.current = create_product("90")

    def test_delegates_enabled_rule_through_registry(self) -> None:
        expected = EvaluationResult(True, "Recorded.", TIMESTAMP)
        evaluator = RecordingEvaluator(RuleType.PRICE_DROP, expected)
        registry = EvaluatorRegistry()
        registry.register(evaluator)
        engine = RuleEngine(registry)

        result = engine.evaluate(
            create_rule(RuleType.PRICE_DROP),
            self.previous,
            self.current,
            TIMESTAMP,
        )

        self.assertIs(result, expected)
        self.assertEqual(evaluator.calls, 1)

    def test_disabled_rule_returns_without_evaluator_lookup(self) -> None:
        evaluator = RecordingEvaluator(
            RuleType.PRICE_DROP,
            EvaluationResult(True, "Should not be returned.", TIMESTAMP),
        )
        registry = EvaluatorRegistry()
        registry.register(evaluator)
        engine = RuleEngine(registry)

        result = engine.evaluate(
            create_rule(RuleType.PRICE_DROP, enabled=False),
            self.previous,
            self.current,
            TIMESTAMP,
        )

        self.assertFalse(result.matched)
        self.assertEqual(result.reason, "Rule is disabled.")
        self.assertEqual(result.timestamp, TIMESTAMP)
        self.assertEqual(evaluator.calls, 0)
