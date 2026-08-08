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
            message=_create_message(product, evaluation),
            created_at=evaluation.timestamp,
        )


def _create_message(product: Product, evaluation: EvaluationResult) -> str:
    availability = "available" if product.availability else "unavailable"
    message = (
        f"{evaluation.reason}\n"
        f"Product: {product.name}\n"
        "Current price: "
        f"{product.current_price.amount} {product.currency.value}\n"
        f"Availability: {availability}\n"
        f"URL: {product.url}"
    )
    if product.original_price is None:
        return message
    return (
        f"{message}\n"
        "Reference price: "
        f"{product.original_price.amount} {product.currency.value}\n"
        f"Discount: {product.discount_percent.value}%"
    )
