"""Daily digest reservation persistence abstraction."""

from datetime import date, datetime
from typing import Protocol


class DailyDigestReservationStore(Protocol):
    """Persist at most one daily digest reservation per calendar date."""

    def reserve(self, calendar_date: date, reserved_at: datetime) -> bool:
        """Atomically reserve a date and report whether it was new."""
        ...

    def release(self, calendar_date: date) -> None:
        """Idempotently release one calendar-date reservation."""
        ...
