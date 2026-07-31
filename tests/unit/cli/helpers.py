"""Deterministic streams and factories for CLI tests."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

TIMESTAMP = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
NOTIFICATION_ID = UUID("80000000-0000-4000-8000-000000000001")


@dataclass(slots=True)
class RecordingStream:
    """Record text writes and explicit flush operations."""

    writes: list[str] = field(default_factory=list)
    flush_count: int = 0

    def write(self, text: str) -> int:
        """Record text and return its accepted length."""
        self.writes.append(text)
        return len(text)

    def flush(self) -> None:
        """Record one flush operation."""
        self.flush_count += 1

    def text(self) -> str:
        """Return all recorded writes as one string."""
        return "".join(self.writes)


def fixed_clock() -> datetime:
    """Return one deterministic timezone-aware timestamp."""
    return TIMESTAMP


def fixed_notification_id() -> UUID:
    """Return one deterministic notification identifier."""
    return NOTIFICATION_ID
