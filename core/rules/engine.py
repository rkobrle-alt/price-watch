"""Rule Engine evaluation coordinator."""

from datetime import datetime

from core.domain import Product, Rule
from core.rules.evaluation import EvaluationResult
from core.rules.registry import EvaluatorRegistry


class RuleEngine:
    """Coordinate side-effect-free evaluation through an evaluator registry."""

    def __init__(self, registry: EvaluatorRegistry) -> None:
        """Create an engine using an explicitly composed evaluator registry."""
        self._registry = registry

    def evaluate(
        self,
        rule: Rule,
        previous: Product | None,
        current: Product,
        timestamp: datetime,
    ) -> EvaluationResult:
        """Evaluate a rule without inspecting evaluator-specific product state."""
        if not rule.enabled:
            return EvaluationResult(
                matched=False,
                reason="Rule is disabled.",
                timestamp=timestamp,
            )
        evaluator = self._registry.get(rule.rule_type)
        return evaluator.evaluate(rule, previous, current, timestamp)
