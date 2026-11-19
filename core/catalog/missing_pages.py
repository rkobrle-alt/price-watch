"""Deterministic lifecycle for temporarily missing product resources."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from core.domain import ProviderId


@dataclass(frozen=True, slots=True)
class MissingProductPage:
    """Retain missing-page evidence and the next permitted retry time."""

    provider_id: ProviderId
    url: str
    failures: int
    checked_at: datetime
    retry_at: datetime

    def __post_init__(self) -> None:
        """Reject invalid identities, counts and chronology."""
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be a ProviderId")
        if not isinstance(self.url, str):
            raise TypeError("url must be a string")
        if not self.url.strip():
            raise ValueError("url cannot be blank")
        if isinstance(self.failures, bool) or not isinstance(self.failures, int):
            raise TypeError("failures must be an int")
        if self.failures <= 0:
            raise ValueError("failures must be positive")
        for value in (self.checked_at, self.retry_at):
            _validate_timestamp(value)
        if self.retry_at <= self.checked_at:
            raise ValueError("retry_at must follow checked_at")


class MissingProductPageStore(Protocol):
    """Persist the complete small collection of missing-page evidence."""

    def load(self) -> tuple[MissingProductPage, ...]:
        """Read validated evidence across providers."""
        ...

    def save(self, pages: tuple[MissingProductPage, ...]) -> None:
        """Atomically replace evidence without changing product history."""
        ...


class MissingPagePolicy:
    """Calculate bounded missing-page retry delays without side effects."""

    def record(
        self, provider_id: ProviderId, url: str, timestamp: datetime,
        previous: MissingProductPage | None = None,
    ) -> MissingProductPage:
        """Advance missing evidence with delays of 6 hours, 1 day and 7 days."""
        _validate_timestamp(timestamp)
        if previous is not None:
            if not isinstance(previous, MissingProductPage):
                raise TypeError("previous must be a MissingProductPage or None")
            if (previous.provider_id, previous.url) != (provider_id, url):
                raise ValueError("previous identity must match")
            if timestamp < previous.checked_at:
                raise ValueError("timestamp cannot precede previous check")
        count = 1 if previous is None else previous.failures + 1
        delay = timedelta(hours=6) if count == 1 else timedelta(days=1 if count == 2 else 7)
        return MissingProductPage(provider_id, url, count, timestamp, timestamp + delay)


def _validate_timestamp(value: object) -> None:
    """Validate a timezone-aware lifecycle timestamp."""
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
