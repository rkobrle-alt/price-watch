"""Percentage value object."""

from dataclasses import dataclass
from decimal import Decimal

from core.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class Percentage:
    """A decimal percentage in the inclusive range from zero to one hundred."""

    value: Decimal

    def __post_init__(self) -> None:
        """Validate the percentage value."""
        if not isinstance(self.value, Decimal):
            raise ValidationError("percentage value must be a Decimal")
        if self.value.is_nan() or self.value.is_infinite():
            raise ValidationError("percentage value must be finite")
        if not Decimal("0") <= self.value <= Decimal("100"):
            raise ValidationError("percentage must be between 0 and 100")
