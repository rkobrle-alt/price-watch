"""Registry mapping rule types to independent evaluators."""

from core.domain import RuleType
from core.rules.evaluator import RuleEvaluator
from core.rules.exceptions import RuleError


class EvaluatorRegistry:
    """Maintain validated evaluators indexed by their supported rule type."""

    def __init__(self) -> None:
        """Create an empty evaluator registry."""
        self._evaluators: dict[RuleType, RuleEvaluator] = {}

    def register(self, evaluator: RuleEvaluator) -> None:
        """Register an evaluator for its single supported rule type."""
        try:
            rule_type = evaluator.rule_type
            supports = evaluator.supports
            evaluate = evaluator.evaluate
        except AttributeError as error:
            raise RuleError("invalid evaluator registration") from error
        if (
            not isinstance(rule_type, RuleType)
            or not callable(supports)
            or not callable(evaluate)
        ):
            raise RuleError("invalid evaluator registration")
        if rule_type in self._evaluators:
            raise RuleError(f"evaluator for {rule_type.value} is already registered")
        self._evaluators[rule_type] = evaluator

    def unregister(self, rule_type: RuleType) -> RuleEvaluator:
        """Remove and return the evaluator registered for a rule type."""
        try:
            return self._evaluators.pop(rule_type)
        except KeyError as error:
            raise RuleError(f"no evaluator registered for {rule_type.value}") from error

    def get(self, rule_type: RuleType) -> RuleEvaluator:
        """Return the evaluator registered for a rule type."""
        try:
            return self._evaluators[rule_type]
        except KeyError as error:
            raise RuleError(f"no evaluator registered for {rule_type.value}") from error

    def list(self) -> tuple[RuleEvaluator, ...]:
        """Return evaluators in registration order."""
        return tuple(self._evaluators.values())
