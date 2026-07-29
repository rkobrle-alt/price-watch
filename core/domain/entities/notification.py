"""Notification entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from core.domain._validation import ensure_timezone_aware
from core.domain.exceptions import ValidationError
from core.domain.value_objects import ProductId


@dataclass(frozen=True, slots=True)
class Notification:
    """An immutable message created for a watched product."""

    id: UUID
    product_id: ProductId
    message: str
    created_at: datetime

    def __post_init__(self) -> None:
        """Validate notification invariants."""
        if not isinstance(self.id, UUID):
            raise ValidationError("notification id must be a UUID")
        ensure_timezone_aware(self.created_at, "created_at")
