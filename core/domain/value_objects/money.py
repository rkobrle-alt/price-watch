"""Monetary value object."""

from dataclasses import dataclass
from decimal import Decimal

from core.domain.enums import Currency
from core.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class Money:
    """A non-negative decimal amount denominated in a supported currency."""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        """Validate the monetary amount and currency."""
        if not isinstance(self.amount, Decimal):
            raise ValidationError("money amount must be a Decimal")
        if self.amount.is_nan() or self.amount.is_infinite():
            raise ValidationError("money amount must be finite")
        if self.amount < Decimal("0"):
            raise ValidationError("money amount cannot be negative")
        if not isinstance(self.currency, Currency):
            raise ValidationError("money currency must be a Currency")
