"""Structural contract for notification delivery channels."""

from typing import Protocol

from core.domain import Notification


class NotificationChannel(Protocol):
    """Contract implemented by concrete notification delivery channels."""

    def send(self, notification: Notification) -> None:
        """Deliver an immutable notification."""
        ...
