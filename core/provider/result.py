"""Provider fetch result value."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.domain import Product, ValidationError
from core.provider.error import ProviderError


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Immutable result of one provider fetch operation."""

    products: tuple[Product, ...]
    started_at: datetime
    finished_at: datetime
    duration: timedelta
    errors: tuple[ProviderError, ...]

    def __post_init__(self) -> None:
        """Validate collection and timing invariants."""
        if not isinstance(self.products, tuple) or not all(
            isinstance(product, Product) for product in self.products
        ):
            raise ValidationError("products must be a tuple of Product instances")
        if not isinstance(self.errors, tuple) or not all(
            isinstance(error, ProviderError) for error in self.errors
        ):
            raise ValidationError("errors must be a tuple of ProviderError instances")
        self._validate_timestamp(self.started_at, "started_at")
        self._validate_timestamp(self.finished_at, "finished_at")
        if self.finished_at < self.started_at:
            raise ValidationError("finished_at cannot be before started_at")
        if not isinstance(self.duration, timedelta):
            raise ValidationError("duration must be a timedelta")
        if self.duration < timedelta(0):
            raise ValidationError("duration cannot be negative")

    @staticmethod
    def _validate_timestamp(value: datetime, field_name: str) -> None:
        if not isinstance(value, datetime):
            raise ValidationError(f"{field_name} must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError(f"{field_name} must be timezone-aware")
