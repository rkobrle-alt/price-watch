"""Pure policy for creating price-drop notification reservations."""

from core.domain import Product, Rule, RuleType
from core.notifications.reservation import NotificationReservation
from core.rules.evaluation import EvaluationResult


class PriceDropReservationPolicy:
    """Create stable identities only for matching price-drop evaluations."""

    def create(
        self,
        rule: Rule,
        product: Product,
        evaluation: EvaluationResult,
    ) -> NotificationReservation | None:
        """Return a reservation for one matching enabled price-drop rule."""
        if not isinstance(rule, Rule):
            raise TypeError("rule must be a Rule")
        if not isinstance(product, Product):
            raise TypeError("product must be a Product")
        if not isinstance(evaluation, EvaluationResult):
            raise TypeError("evaluation must be an EvaluationResult")
        if (
            not rule.enabled
            or rule.rule_type is not RuleType.PRICE_DROP
            or not evaluation.matched
        ):
            return None
        return NotificationReservation(
            product_id=product.id,
            rule_type=rule.rule_type,
            price=product.current_price,
        )
