"""Product entity."""

from dataclasses import dataclass
from datetime import datetime

from core.domain._validation import ensure_non_blank, ensure_timezone_aware
from core.domain.enums import Currency
from core.domain.exceptions import ValidationError
from core.domain.value_objects import Money, Percentage, ProductId, ProviderId


@dataclass(frozen=True, slots=True)
class Product:
    """An immutable product offered by a provider."""

    id: ProductId
    provider_id: ProviderId
    brand: str
    name: str
    current_price: Money
    original_price: Money | None
    discount_percent: Percentage
    url: str
    image_url: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        """Validate product invariants."""
        ensure_non_blank(self.name, "product name")
        ensure_timezone_aware(self.created_at, "created_at")
        if self.original_price is not None:
            if not isinstance(self.original_price, Money):
                raise ValidationError("original_price must be Money or None")
            if self.original_price.currency is not self.current_price.currency:
                raise ValidationError("product prices must use the same currency")

    @property
    def currency(self) -> Currency:
        """Return the currency shared by the product's prices."""
        return self.current_price.currency
