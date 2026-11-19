"""Immutable assessments of retained, observed prices."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum

from core.domain import Money, ProductId


class PriceValueRating(str, Enum):
    """Describe value relative to observed daily closing prices."""

    EXCELLENT = "excellent"
    GOOD = "good"
    LOWER = "lower"
    NORMAL = "normal"
    ABOVE_USUAL = "above_usual"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class PriceHistoryAssessment:
    """Expose observed minima, daily-median context and evidence coverage."""

    product_id: ProductId
    current_price: Money
    observed_at: datetime
    assessed_at: datetime
    first_observed_at: datetime | None
    history_days: int
    observed_days_30: int
    observed_days_90: int
    prior_days: int
    minimum_30: Money | None
    minimum_90: Money | None
    usual_price: Money | None
    saving_vs_usual_percent: Decimal | None
    last_price_drop_on: date | None
    rating: PriceValueRating

    def __post_init__(self) -> None:
        """Validate identities, units, sample counts and evidence types."""
        if not isinstance(self.product_id, ProductId):
            raise TypeError("product_id must be a ProductId")
        if not isinstance(self.current_price, Money):
            raise TypeError("current_price must be Money")
        if not isinstance(self.rating, PriceValueRating):
            raise TypeError("rating must be a PriceValueRating")
        _validate_timestamp(self.observed_at)
        _validate_timestamp(self.assessed_at)
        if self.first_observed_at is not None:
            _validate_timestamp(self.first_observed_at)
            if self.first_observed_at.astimezone(UTC) > self.assessed_at.astimezone(UTC):
                raise ValueError("first observation cannot follow assessment")
        for count in (self.history_days, self.observed_days_30, self.observed_days_90, self.prior_days):
            if isinstance(count, bool) or not isinstance(count, int):
                raise TypeError("history counts must be integers")
            if count < 0:
                raise ValueError("history counts cannot be negative")
        if not self.observed_days_30 <= min(30, self.observed_days_90) or self.observed_days_90 > min(90, self.history_days) or self.prior_days > min(89, self.observed_days_90):
            raise ValueError("observed-day counts exceed their evidence windows")
        if (self.first_observed_at is None) != (self.history_days == 0):
            raise ValueError("history span requires a first observation")
        for money in (self.minimum_30, self.minimum_90, self.usual_price):
            if money is not None:
                if not isinstance(money, Money):
                    raise TypeError("history prices must be Money or None")
                if money.currency is not self.current_price.currency:
                    raise ValueError("history prices must use the current currency")
        saving = self.saving_vs_usual_percent
        if saving is not None:
            if not isinstance(saving, Decimal):
                raise TypeError("saving must be Decimal or None")
            if not saving.is_finite():
                raise ValueError("saving must be finite")
        if self.last_price_drop_on is not None and (
            not isinstance(self.last_price_drop_on, date) or isinstance(self.last_price_drop_on, datetime)
        ):
            raise TypeError("last_price_drop_on must be a date or None")


def _validate_timestamp(value: object) -> None:
    """Validate an aware timestamp without consulting a clock."""
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
