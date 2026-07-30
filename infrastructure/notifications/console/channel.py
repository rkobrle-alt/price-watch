"""Console notification delivery channel."""

from typing import TextIO

from core.domain import Notification
from core.notifications import NotificationError


class ConsoleNotificationChannel:
    """Deliver notifications to an explicitly injected text stream."""

    def __init__(self, stream: TextIO) -> None:
        """Create a channel using a validated writable, flushable stream."""
        if not callable(getattr(stream, "write", None)) or not callable(
            getattr(stream, "flush", None)
        ):
            raise TypeError("stream must expose callable write and flush members")
        self._stream = stream

    def send(self, notification: Notification) -> None:
        """Write and flush one deterministic line for a notification."""
        if not isinstance(notification, Notification):
            raise TypeError("notification must be a Notification")
        line = (
            f"{notification.created_at.isoformat()} "
            f"{notification.product_id.value} "
            f"{notification.message}\n"
        )
        try:
            self._stream.write(line)
            self._stream.flush()
        except (OSError, ValueError) as error:
            raise NotificationError("console notification delivery failed") from error
