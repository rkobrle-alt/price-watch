"""Provider-neutral current-promotion source contract."""

from typing import Protocol

from core.promotions.model import DailyPromotion


class DailyPromotionSource(Protocol):
    """Load the provider's current daily promotion when one exists."""

    def current(self) -> DailyPromotion | None:
        """Return the current promotion or no published promotion."""
        ...
