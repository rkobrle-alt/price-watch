"""Immutable daily digest application outcome."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from core.provider import ProviderError


class DailyDigestStatus(str, Enum):
    """Classify one daily digest workflow outcome."""

    NOT_DUE = "not_due"
    ALREADY_SENT = "already_sent"
    PROMOTION_UNAVAILABLE = "promotion_unavailable"
    SENT = "sent"


@dataclass(frozen=True, slots=True)
class DailyDigestResult:
    """Report calendar eligibility and delivered product count."""

    calendar_date: date
    status: DailyDigestStatus
    product_count: int = 0
    promotion_included: bool = False
    refresh_errors: tuple[ProviderError, ...] = ()

    def __post_init__(self) -> None:
        """Validate result values and count semantics."""
        if not isinstance(self.refresh_errors, tuple) or not all(
            isinstance(error, ProviderError) for error in self.refresh_errors
        ):
            raise TypeError("refresh_errors must be a tuple of ProviderError")
        if isinstance(self.calendar_date, datetime) or not isinstance(
            self.calendar_date,
            date,
        ):
            raise TypeError("calendar_date must be a date")
        if not isinstance(self.status, DailyDigestStatus):
            raise TypeError("status must be a DailyDigestStatus")
        if self.status is not DailyDigestStatus.SENT and self.refresh_errors:
            raise ValueError("non-delivery result cannot contain refresh errors")
        if isinstance(self.product_count, bool) or not isinstance(
            self.product_count,
            int,
        ):
            raise TypeError("product_count must be an int")
        if self.product_count < 0:
            raise ValueError("product_count cannot be negative")
        if self.status is not DailyDigestStatus.SENT and self.product_count:
            raise ValueError("non-delivery result cannot contain products")
        if not isinstance(self.promotion_included, bool):
            raise TypeError("promotion_included must be a bool")
        if self.status is not DailyDigestStatus.SENT and self.promotion_included:
            raise ValueError("non-delivery result cannot include a promotion")
