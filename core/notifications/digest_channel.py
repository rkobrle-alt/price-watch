"""Daily digest delivery abstraction."""

from typing import Protocol

from core.notifications.daily_digest import DailyDiscountDigest


class DailyDiscountDigestChannel(Protocol):
    """Deliver immutable daily discount digests."""

    def send(self, digest: DailyDiscountDigest) -> None:
        """Deliver one digest or raise a notification subsystem error."""
        ...
