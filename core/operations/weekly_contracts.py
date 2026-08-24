"""Weekly operational persistence and delivery boundaries."""

from datetime import date
from typing import Protocol

from core.operations.weekly import WeeklyOperationalReport, WeeklyOperationalSummary


class WeeklyOperationalSummaryStore(Protocol):
    """Load and save durable weekly operational buckets."""

    def load(self, period_start: date) -> WeeklyOperationalSummary | None:
        """Return one retained bucket or None when absent."""
        ...

    def save(self, summary: WeeklyOperationalSummary) -> None:
        """Atomically retain one complete bucket."""
        ...


class WeeklyOperationalSummaryChannel(Protocol):
    """Deliver one channel-neutral weekly operational report."""

    def send(self, report: WeeklyOperationalReport) -> None:
        """Deliver one validated weekly report."""
        ...
