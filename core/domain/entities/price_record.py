"""Historical product price entity."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.domain._validation import ensure_timezone_aware
from core.domain.enums import Currency
from core.domain.exceptions import ValidationError
from core.domain.value_objects import ProductId


@dataclass(frozen=True, slots=True)
class PriceRecord:
    """An immutable observation of a product price at a point in time."""

    product_id: ProductId
    price: Decimal
    currency: Currency
    captured_at: datetime

    def __post_init__(self) -> None:
        """Validate the recorded price and timestamp."""
        if not isinstance(self.price, Decimal):
            raise ValidationError("price must be a Decimal")
        if self.price.is_nan() or self.price.is_infinite():
            raise ValidationError("price must be finite")
        if self.price < Decimal("0"):
            raise ValidationError("price cannot be negative")
        if not isinstance(self.currency, Currency):
            raise ValidationError("currency must be a Currency")
        ensure_timezone_aware(self.captured_at, "captured_at")
