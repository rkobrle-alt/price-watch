"""Immutable price-alert reservation and persistence boundary."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from core.domain import Money, ProductId, RuleType


@dataclass(frozen=True, slots=True)
class NotificationReservation:
    """Identify one logical notification by product, rule and current price."""

    product_id: ProductId
    rule_type: RuleType
    price: Money

    def __post_init__(self) -> None:
        """Validate structured reservation identity values."""
        if not isinstance(self.product_id, ProductId):
            raise TypeError("product_id must be a ProductId")
        if not isinstance(self.rule_type, RuleType):
            raise TypeError("rule_type must be a RuleType")
        if not isinstance(self.price, Money):
            raise TypeError("price must be Money")


class NotificationReservationStore(Protocol):
    """Persist unique logical notification reservations."""

    def reserve(
        self,
        reservation: NotificationReservation,
        reserved_at: datetime,
    ) -> bool:
        """Atomically reserve an identity and report whether it was new."""
        ...

    def release(self, reservation: NotificationReservation) -> None:
        """Idempotently release one logical notification reservation."""
        ...
