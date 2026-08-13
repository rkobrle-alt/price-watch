"""Public provider-neutral daily promotion API."""

from core.promotions.exceptions import PromotionError
from core.promotions.model import DailyPromotion
from core.promotions.source import DailyPromotionSource

__all__ = ["DailyPromotion", "DailyPromotionSource", "PromotionError"]
