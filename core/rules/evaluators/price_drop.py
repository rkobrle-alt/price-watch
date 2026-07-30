"""Evaluator for product price decreases."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from core.domain import Currency, Money, Percentage, Product, Rule, RuleType
from core.rules.evaluation import EvaluationResult
from core.rules.exceptions import RuleError


@dataclass(frozen=True, slots=True)
class PriceDropEvaluator:
    """Match price decreases that satisfy configured optional thresholds."""

    rule_type: RuleType = field(init=False, default=RuleType.PRICE_DROP)

    def evaluate(
        self,
        rule: Rule,
        previous: Product | None,
        current: Product,
        timestamp: datetime,
    ) -> EvaluationResult:
        """Evaluate a current price against its previous product state."""
        if previous is None:
            return EvaluationResult(False, "Previous product state is unavailable.", timestamp)
        if previous.currency is not current.currency:
            return EvaluationResult(False, "Product currencies do not match.", timestamp)

        drop = previous.current_price.amount - current.current_price.amount
        if drop <= Decimal("0"):
            return EvaluationResult(False, "Product price did not decrease.", timestamp)

        fixed_threshold = self._fixed_threshold(rule, current.currency)
        if fixed_threshold is not None and drop < fixed_threshold:
            return EvaluationResult(False, "Price drop is below the fixed threshold.", timestamp)

        percentage_threshold = self._percentage_threshold(rule)
        percentage_drop = drop * Decimal("100") / previous.current_price.amount
        if (
            percentage_threshold is not None
            and percentage_drop < percentage_threshold
        ):
            return EvaluationResult(
                False,
                "Price drop is below the percentage threshold.",
                timestamp,
            )
        return EvaluationResult(True, "Product price decreased.", timestamp)

    @staticmethod
    def _fixed_threshold(rule: Rule, currency: Currency) -> Decimal | None:
        value = rule.parameters.get("fixed_amount")
        if value is None:
            return None
        if isinstance(value, Money):
            if value.currency is not currency:
                raise RuleError("fixed_amount currency must match the product currency")
            return value.amount
        if isinstance(value, Decimal) and value >= Decimal("0"):
            return value
        raise RuleError("fixed_amount must be non-negative Decimal or Money")

    @staticmethod
    def _percentage_threshold(rule: Rule) -> Decimal | None:
        value = rule.parameters.get("percentage")
        if value is None:
            return None
        if isinstance(value, Percentage):
            return value.value
        if (
            isinstance(value, Decimal)
            and Decimal("0") <= value <= Decimal("100")
        ):
            return value
        raise RuleError("percentage must be Decimal or Percentage between 0 and 100")
