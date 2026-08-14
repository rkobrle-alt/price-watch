"""Immutable operational monitoring workflow result."""

from dataclasses import dataclass

from core.operations import (
    OperationalNotificationError,
    OperationalNotificationKind,
    OperationalState,
)


@dataclass(frozen=True, slots=True)
class OperationalMonitoringResult:
    """Report saved state and optional notification-delivery outcome."""

    state: OperationalState
    notification_sent: OperationalNotificationKind | None = None
    notification_error: OperationalNotificationError | None = None

    def __post_init__(self) -> None:
        """Validate mutually exclusive delivery diagnostics."""
        if not isinstance(self.state, OperationalState):
            raise TypeError("state must be an OperationalState")
        if self.notification_sent is not None and not isinstance(
            self.notification_sent,
            OperationalNotificationKind,
        ):
            raise TypeError(
                "notification_sent must be an OperationalNotificationKind or None"
            )
        if self.notification_error is not None and not isinstance(
            self.notification_error,
            OperationalNotificationError,
        ):
            raise TypeError(
                "notification_error must be an OperationalNotificationError or None"
            )
        if self.notification_sent is not None and self.notification_error is not None:
            raise ValueError("notification result values are mutually exclusive")
