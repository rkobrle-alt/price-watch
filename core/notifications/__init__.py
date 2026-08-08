"""Public API for deterministic notification generation and delivery contracts."""

from core.notifications.channel import NotificationChannel
from core.notifications.daily_digest import (
    DailyDiscountDigest,
    DailyDiscountDigestEngine,
)
from core.notifications.digest_channel import DailyDiscountDigestChannel
from core.notifications.digest_reservation import DailyDigestReservationStore
from core.notifications.engine import NotificationEngine
from core.notifications.exceptions import (
    DailyDigestReservationError,
    NotificationError,
    NotificationReservationError,
)
from core.notifications.reservation import (
    NotificationReservation,
    NotificationReservationStore,
)
from core.notifications.reservation_policy import PriceDropReservationPolicy

__all__ = [
    "DailyDigestReservationError",
    "DailyDigestReservationStore",
    "DailyDiscountDigest",
    "DailyDiscountDigestChannel",
    "DailyDiscountDigestEngine",
    "NotificationChannel",
    "NotificationEngine",
    "NotificationError",
    "NotificationReservation",
    "NotificationReservationError",
    "NotificationReservationStore",
    "PriceDropReservationPolicy",
]
