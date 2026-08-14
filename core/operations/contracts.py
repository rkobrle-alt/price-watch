"""Operational persistence and delivery boundaries."""

from typing import Protocol

from core.operations.model import OperationalNotification, OperationalState


class OperationalStateStore(Protocol):
    """Load and save one durable operational state."""

    def load(self) -> OperationalState:
        """Return the current state or the canonical initial state."""
        ...

    def save(self, state: OperationalState) -> None:
        """Atomically persist the complete state."""
        ...


class OperationalNotificationChannel(Protocol):
    """Deliver channel-neutral operational transition messages."""

    def send(self, notification: OperationalNotification) -> None:
        """Deliver one validated operational notification."""
        ...
