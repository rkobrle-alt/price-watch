"""Deterministic fakes and factories for synchronization tests."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from core.domain import (
    Currency,
    Money,
    Notification,
    Percentage,
    Product,
    ProductId,
    ProviderId,
    Rule,
    RuleType,
)
from core.provider import FetchResult, ProviderError
from core.rules import EvaluationResult
from core.state import StateSnapshot

TIMESTAMP = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
PREVIOUS_TIMESTAMP = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
PROVIDER_ID = ProviderId(UUID("10000000-0000-4000-8000-000000000001"))
NOTIFICATION_IDS = (
    UUID("20000000-0000-4000-8000-000000000001"),
    UUID("20000000-0000-4000-8000-000000000002"),
    UUID("20000000-0000-4000-8000-000000000003"),
    UUID("20000000-0000-4000-8000-000000000004"),
)


def create_product(
    index: int = 1,
    *,
    amount: str = "90.00",
    availability: bool = True,
) -> Product:
    """Create a deterministic product with a selectable identity and state."""
    return Product(
        id=ProductId(UUID(f"30000000-0000-4000-8000-{index:012d}")),
        provider_id=PROVIDER_ID,
        brand="PARKSIDE",
        name=f"Tool {index}",
        current_price=Money(Decimal(amount), Currency.CZK),
        original_price=None,
        discount_percent=Percentage(Decimal("0")),
        url=f"https://www.lidl.cz/tool-{index}/p{index}",
        image_url=None,
        created_at=TIMESTAMP,
        availability=availability,
    )


def create_rule(name: str = "match") -> Rule:
    """Create a deterministic enabled rule interpreted by the fake engine."""
    return Rule(
        id=UUID("40000000-0000-4000-8000-000000000001"),
        name=name,
        enabled=True,
        rule_type=RuleType.PRICE_DROP,
    )


def create_fetch_result(
    products: tuple[Product, ...] = (),
    errors: tuple[ProviderError, ...] = (),
) -> FetchResult:
    """Create a deterministic provider result."""
    return FetchResult(
        products=products,
        started_at=TIMESTAMP,
        finished_at=TIMESTAMP + timedelta(seconds=1),
        duration=timedelta(seconds=1),
        errors=errors,
    )


@dataclass(slots=True)
class RecordingProvider:
    """Return a configured result or raise a configured provider failure."""

    name: str
    events: list[str]
    outcome: FetchResult | Exception
    id: ProviderId = PROVIDER_ID
    display_name: str = "Test Provider"
    version: str = "1.0"

    def fetch(self) -> FetchResult:
        """Record retrieval and return or raise the configured outcome."""
        self.events.append(f"fetch:{self.name}")
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@dataclass(slots=True)
class RecordingStateStore:
    """Record state operations in memory."""

    events: list[str]
    values: dict[ProductId, StateSnapshot] = field(default_factory=dict)
    load_error: Exception | None = None
    save_error: Exception | None = None

    def load(self, product_id: ProductId) -> StateSnapshot | None:
        """Record and return a configured previous snapshot."""
        self.events.append(f"load:{product_id.value}")
        if self.load_error is not None:
            raise self.load_error
        return self.values.get(product_id)

    def save(self, snapshot: StateSnapshot) -> None:
        """Record and retain a current snapshot unless configured to fail."""
        self.events.append(f"save:{snapshot.product.id.value}")
        if self.save_error is not None:
            raise self.save_error
        self.values[snapshot.product.id] = snapshot


@dataclass(slots=True)
class RecordingRuleEngine:
    """Return matches selected by rule name while recording inputs."""

    events: list[str]
    previous_products: list[Product | None] = field(default_factory=list)
    error: Exception | None = None

    def evaluate(
        self,
        rule: Rule,
        previous: Product | None,
        current: Product,
        timestamp: datetime,
    ) -> EvaluationResult:
        """Record an evaluation and optionally fail."""
        self.events.append(f"evaluate:{rule.name}:{current.id.value}")
        self.previous_products.append(previous)
        if self.error is not None:
            raise self.error
        return EvaluationResult(
            matched=rule.name == "match",
            reason=f"result:{rule.name}",
            timestamp=timestamp,
        )


@dataclass(slots=True)
class RecordingNotificationEngine:
    """Generate notifications for matching recorded evaluations."""

    events: list[str]
    error: Exception | None = None

    def generate(
        self,
        product: Product,
        evaluation: EvaluationResult,
        notification_id: UUID,
    ) -> Notification | None:
        """Record generation and mirror the Core generation contract."""
        self.events.append(f"generate:{evaluation.matched}:{product.id.value}")
        if self.error is not None:
            raise self.error
        if not evaluation.matched:
            return None
        return Notification(
            id=notification_id,
            product_id=product.id,
            message=evaluation.reason,
            created_at=evaluation.timestamp,
        )


@dataclass(slots=True)
class RecordingChannel:
    """Record delivered notifications and optionally fail."""

    events: list[str]
    sent: list[Notification] = field(default_factory=list)
    error: Exception | None = None

    def send(self, notification: Notification) -> None:
        """Record delivery before optionally raising an error."""
        self.events.append(f"send:{notification.product_id.value}")
        if self.error is not None:
            raise self.error
        self.sent.append(notification)


@dataclass(slots=True)
class RecordingIdFactory:
    """Return deterministic UUID values and record each request."""

    events: list[str]
    values: list[UUID] = field(default_factory=lambda: list(NOTIFICATION_IDS))
    error: Exception | None = None

    def __call__(self) -> UUID:
        """Return the next configured identifier or raise a failure."""
        self.events.append("notification_id")
        if self.error is not None:
            raise self.error
        return self.values.pop(0)
