"""Evaluator for product availability transitions."""

from dataclasses import dataclass, field
from datetime import datetime

from core.domain import Product, Rule, RuleType
from core.rules.evaluation import EvaluationResult


@dataclass(frozen=True, slots=True)
class BackInStockEvaluator:
    """Match an unavailable-to-available product transition."""

    rule_type: RuleType = field(init=False, default=RuleType.BACK_IN_STOCK)

    def supports(self, rule: Rule) -> bool:
        """Return whether the rule is a back-in-stock rule."""
        return rule.rule_type is self.rule_type

    def evaluate(
        self,
        rule: Rule,
        previous: Product | None,
        current: Product,
        timestamp: datetime,
    ) -> EvaluationResult:
        """Evaluate whether the product has just become available."""
        if previous is None:
            return EvaluationResult(False, "Previous product state is unavailable.", timestamp)
        if previous.availability:
            return EvaluationResult(False, "Product was already available.", timestamp)
        if not current.availability:
            return EvaluationResult(False, "Product remains unavailable.", timestamp)
        return EvaluationResult(True, "Product is back in stock.", timestamp)
