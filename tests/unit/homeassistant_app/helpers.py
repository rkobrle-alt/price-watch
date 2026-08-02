"""Deterministic helpers for Home Assistant application tests."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from applications.configuration import ApplicationConfig
from applications.homeassistant import HomeAssistantConfig

TIMESTAMP = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
PRODUCT_URL = "https://www.lidl.cz/p/parkside-test-tool/p100382709"


def create_options(**overrides: object) -> dict[str, object]:
    """Create a complete valid Supervisor option mapping."""
    options: dict[str, object] = {
        "product_urls": [PRODUCT_URL],
        "notify_entity": "notify.gmail_parkside",
        "interval_seconds": 300,
    }
    options.update(overrides)
    return options


def create_config(
    *,
    percentage: Decimal | None = Decimal("10.00"),
    amount: Decimal | None = None,
) -> HomeAssistantConfig:
    """Create a complete immutable App configuration."""
    return HomeAssistantConfig(
        application=ApplicationConfig(
            product_urls=(PRODUCT_URL,),
            state_file=Path("/data/state.json"),
            timeout_seconds=12,
            price_drop_percentage=percentage,
            price_drop_amount=amount,
            interval=timedelta(seconds=300),
        ),
        notify_entity="notify.gmail_parkside",
        notification_title="Parkside Price Watch",
    )


@dataclass(slots=True)
class RecordingStream:
    """Record process text and flushes."""

    writes: list[str] = field(default_factory=list)
    flush_count: int = 0

    def write(self, text: str) -> int:
        """Record text and return its length."""
        self.writes.append(text)
        return len(text)

    def flush(self) -> None:
        """Record a flush."""
        self.flush_count += 1

    @property
    def text(self) -> str:
        """Return all recorded text."""
        return "".join(self.writes)


@dataclass(slots=True)
class RecordingDelay:
    """Record fixed-delay requests without sleeping."""

    durations: list[timedelta] = field(default_factory=list)
    failure: BaseException | None = None

    def wait(self, duration: timedelta) -> None:
        """Record the duration and optionally fail."""
        self.durations.append(duration)
        if self.failure is not None:
            raise self.failure
