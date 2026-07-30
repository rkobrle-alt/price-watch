"""Deterministic notification generation service."""

from uuid import UUID

from core.domain import Notification, Product
from core.rules import EvaluationResult


class NotificationEngine:
    """Generate immutable notifications without side effects."""

    def generate(
        self,
        product: Product,
        evaluation: EvaluationResult,
        notification_id: UUID,
    ) -> Notification | None:
        """Generate a notification when the supplied evaluation matched."""
        if not isinstance(product, Product):
            raise TypeError("product must be a Product")
        if not isinstance(evaluation, EvaluationResult):
            raise TypeError("evaluation must be an EvaluationResult")
        if not isinstance(notification_id, UUID):
            raise TypeError("notification_id must be a UUID")
        if not evaluation.matched:
            return None
        return Notification(
            id=notification_id,
            product_id=product.id,
            message=evaluation.reason,
            created_at=evaluation.timestamp,
        )
