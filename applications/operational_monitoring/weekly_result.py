"""Immutable weekly operational workflow result."""

from dataclasses import dataclass

from core.operations import (
    OperationalNotificationError,
    WeeklyOperationalReport,
    WeeklyOperationalSummary,
)


@dataclass(frozen=True, slots=True)
class WeeklyOperationalSummaryResult:
    """Report current aggregation and optional weekly delivery outcome."""

    current_summary: WeeklyOperationalSummary
    report_sent: WeeklyOperationalReport | None = None
    notification_error: OperationalNotificationError | None = None

    def __post_init__(self) -> None:
        """Validate result values and mutual exclusivity."""
        if not isinstance(self.current_summary, WeeklyOperationalSummary):
            raise TypeError("current_summary must be a WeeklyOperationalSummary")
        if self.report_sent is not None and not isinstance(
            self.report_sent,
            WeeklyOperationalReport,
        ):
            raise TypeError("report_sent must be a WeeklyOperationalReport or None")
        if self.notification_error is not None and not isinstance(
            self.notification_error,
            OperationalNotificationError,
        ):
            raise TypeError(
                "notification_error must be an OperationalNotificationError or None"
            )
        if self.report_sent is not None and self.notification_error is not None:
            raise ValueError("weekly delivery result values are mutually exclusive")
