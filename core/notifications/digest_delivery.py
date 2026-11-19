"""Delivery evidence and bounded promotion fallback contracts."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Protocol

from core.notifications.daily_digest import DailyDiscountDigest
from core.notifications.exceptions import NotificationError


class NotificationDeliveryRejectedError(NotificationError):
    """Report a request known to be rejected before notification execution."""


class DigestDeliveryPhase(str, Enum):
    """Distinguish preparation, external handoff and uncertain results."""

    READY = "ready"
    PREPARING = "preparing"
    SENDING = "sending"
    ACCEPTED = "accepted"
    UNCERTAIN = "uncertain"
    LEGACY_RESERVED = "legacy_reserved"


@dataclass(frozen=True, slots=True)
class DigestDeliveryRecord:
    """Retain evidence without claiming destination-mailbox delivery."""

    calendar_date: date
    phase: DigestDeliveryPhase
    updated_at: datetime
    product_count: int = 0
    promotion_included: bool = False
    promotion_missing: bool = False

    def __post_init__(self) -> None:
        """Validate evidence types and noncontradictory promotion metadata."""
        if not isinstance(self.calendar_date, date) or isinstance(self.calendar_date, datetime):
            raise TypeError("calendar_date must be a date")
        if not isinstance(self.phase, DigestDeliveryPhase):
            raise TypeError("phase must be a DigestDeliveryPhase")
        _validate_timestamp(self.updated_at)
        if isinstance(self.product_count, bool) or not isinstance(self.product_count, int):
            raise TypeError("product_count must be an int")
        if self.product_count < 0:
            raise ValueError("product_count cannot be negative")
        if not isinstance(self.promotion_included, bool) or not isinstance(self.promotion_missing, bool):
            raise TypeError("promotion flags must be bool")
        if self.promotion_included and self.promotion_missing:
            raise ValueError("included promotion cannot be missing")


class DigestDeliveryStore(Protocol):
    """Persist evidence under one serialized App process; not a worker queue."""

    def recover(self, timestamp: datetime) -> None:
        """Recover abandoned preparation and mark interrupted handoff uncertain."""
        ...

    def claim(self, calendar_date: date, timestamp: datetime) -> DigestDeliveryPhase:
        """Atomically claim a new/ready date or return its retained phase."""
        ...

    def transition(
        self, calendar_date: date, expected: DigestDeliveryPhase,
        phase: DigestDeliveryPhase, timestamp: datetime, *, product_count: int = 0,
        promotion_included: bool = False, promotion_missing: bool = False,
    ) -> None:
        """Compare the expected phase and commit the next evidence atomically."""
        ...

    def latest(self) -> DigestDeliveryRecord | None:
        """Read evidence for the newest retained local calendar date."""
        ...


class DigestPromotionPolicy:
    """Bound optional banner delays without inventing marketing information."""

    def can_fallback(self, timestamp: datetime, scheduled_at: datetime) -> bool:
        """Permit fallback at least 30 minutes after scheduled eligibility."""
        _validate_timestamp(timestamp)
        _validate_timestamp(scheduled_at)
        return timestamp - scheduled_at >= timedelta(minutes=30)

    def fallback_digest(self, digest: DailyDiscountDigest) -> DailyDiscountDigest:
        """Insert an explicit Czech notice into a digest without a promotion."""
        if not isinstance(digest, DailyDiscountDigest):
            raise TypeError("digest must be a DailyDiscountDigest")
        if digest.promotion is not None:
            raise ValueError("fallback digest cannot include a promotion")
        heading, _, rest = digest.message.partition("\n")
        warning = "Dnešní akci Lidlu se nepodařilo ověřit. Přehled slev odesíláme bez reklamního banneru."
        return replace(digest, message=f"{heading}\n{warning}\n{rest}")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
