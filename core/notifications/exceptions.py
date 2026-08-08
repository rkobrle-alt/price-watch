"""Notification subsystem exception contract."""


class NotificationError(Exception):
    """Base exception for operational notification delivery failures."""


class NotificationReservationError(Exception):
    """Report persistence failures for notification reservations."""


class DailyDigestReservationError(Exception):
    """Report persistence failures for daily digest reservations."""
