"""Structural contract for independent rule evaluators."""

from datetime import datetime
from typing import Protocol

from core.domain import Product, Rule, RuleType
from core.rules.evaluation import EvaluationResult


class RuleEvaluator(Protocol):
    """Contract implemented by one RuleType-specific evaluator."""

    rule_type: RuleType

    def supports(self, rule: Rule) -> bool:
        """Return whether this evaluator handles the supplied rule."""
        ...

    def evaluate(
        self,
        rule: Rule,
        previous: Product | None,
        current: Product,
        timestamp: datetime,
    ) -> EvaluationResult:
        """Evaluate a supported rule against immutable product states."""
        ...
