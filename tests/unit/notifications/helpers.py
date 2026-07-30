"""Typed factories and streams for notification tests."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from core.domain import (
    Currency,
    Money,
    Percentage,
    Product,
    ProductId,
    ProviderId,
)
from core.rules import EvaluationResult

TIMESTAMP = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
NOTIFICATION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
PRODUCT_ID = ProductId(UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))


def create_product() -> Product:
    """Create a deterministic product for notification generation tests."""
    return Product(
        id=PRODUCT_ID,
        provider_id=ProviderId(UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")),
        brand="Example",
        name="Coffee",
        current_price=Money(Decimal("99.90"), Currency.CZK),
        original_price=None,
        discount_percent=Percentage(Decimal("0")),
        url="https://example.test/product",
        image_url=None,
        created_at=TIMESTAMP,
    )


def create_evaluation(*, matched: bool = True) -> EvaluationResult:
    """Create a deterministic rule evaluation result."""
    return EvaluationResult(
        matched=matched,
        reason="Product price decreased.",
        timestamp=TIMESTAMP,
    )


@dataclass(slots=True)
class RecordingStream:
    """Record text writes and flush calls without real I/O."""

    writes: list[str] = field(default_factory=list)
    flush_count: int = 0

    def write(self, text: str) -> int:
        """Record text and report the accepted character count."""
        self.writes.append(text)
        return len(text)

    def flush(self) -> None:
        """Record a flush operation."""
        self.flush_count += 1


class WriteFailingStream:
    """Raise an operational error while writing."""

    def write(self, text: str) -> int:
        """Fail before accepting text."""
        raise OSError("write failed")

    def flush(self) -> None:
        """Provide the required stream member."""
        raise AssertionError("flush must not be called after write failure")


class FlushFailingStream(RecordingStream):
    """Accept text and fail while flushing it."""

    def flush(self) -> None:
        """Raise a closed-stream style failure."""
        raise ValueError("flush failed")
