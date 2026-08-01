"""End-to-end component integration for durable Lidl synchronization."""

import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from uuid import UUID

from applications.synchronization import SynchronizationWorkflow
from core.domain import Rule, RuleType
from core.notifications import NotificationEngine
from core.rules import EvaluatorRegistry, RuleEngine
from core.rules.evaluators import BackInStockEvaluator, PriceDropEvaluator
from infrastructure.notifications.console import ConsoleNotificationChannel
from infrastructure.persistence.json import JsonStateStore
from infrastructure.providers.lidl import LidlParksideProvider

PRODUCT_URL = "https://www.lidl.cz/parkside-test/p100"
TIMESTAMP = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


class MutableTextHttpClient:
    """Return mutable in-memory Lidl page content without network access."""

    def __init__(self, content: str) -> None:
        """Configure initial page content."""
        self.content = content

    def get(self, url: str) -> str:
        """Return the configured page for the expected URL."""
        assert url == PRODUCT_URL
        return self.content


class NotificationIdSequence:
    """Return deterministic notification IDs across synchronization runs."""

    def __init__(self) -> None:
        """Create four IDs for two rules evaluated twice."""
        self._values = iter(
            UUID(f"50000000-0000-4000-8000-{index:012d}")
            for index in range(1, 5)
        )

    def __call__(self) -> UUID:
        """Return the next deterministic identifier."""
        return next(self._values)


def _page(*, price: str, availability: str) -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "sku": "PARKSIDE-100",
        "name": "Parkside Test Tool",
        "brand": {"@type": "Brand", "name": "PARKSIDE"},
        "offers": {
            "@type": "Offer",
            "price": price,
            "priceCurrency": "CZK",
            "availability": f"https://schema.org/{availability}",
        },
    }
    return (
        '<html><script type="application/ld+json">'
        f"{json.dumps(product)}"
        "</script></html>"
    )


def _rule_engine() -> RuleEngine:
    registry = EvaluatorRegistry()
    registry.register(PriceDropEvaluator())
    registry.register(BackInStockEvaluator())
    return RuleEngine(registry)


def _rules() -> tuple[Rule, ...]:
    return (
        Rule(
            id=UUID("60000000-0000-4000-8000-000000000001"),
            name="Price drop",
            enabled=True,
            rule_type=RuleType.PRICE_DROP,
        ),
        Rule(
            id=UUID("60000000-0000-4000-8000-000000000002"),
            name="Back in stock",
            enabled=True,
            rule_type=RuleType.BACK_IN_STOCK,
        ),
    )


def test_second_process_detects_persisted_price_and_availability_changes(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "price-watch" / "state.json"
    http_client = MutableTextHttpClient(
        _page(price="100.00", availability="OutOfStock")
    )
    provider = LidlParksideProvider(
        (PRODUCT_URL,),
        http_client,
        lambda: TIMESTAMP,
    )
    output = StringIO()
    channel = ConsoleNotificationChannel(output)
    notification_ids = NotificationIdSequence()

    first_workflow = SynchronizationWorkflow(
        providers=(provider,),
        state_store=JsonStateStore(state_path),
        rule_engine=_rule_engine(),
        notification_engine=NotificationEngine(),
        notification_channel=channel,
        notification_id_factory=notification_ids,
    )
    first_result = first_workflow.run(_rules(), TIMESTAMP)

    assert first_result.notifications == ()
    assert state_path.is_file()

    http_client.content = _page(price="80.00", availability="InStock")
    second_workflow = SynchronizationWorkflow(
        providers=(provider,),
        state_store=JsonStateStore(state_path),
        rule_engine=_rule_engine(),
        notification_engine=NotificationEngine(),
        notification_channel=channel,
        notification_id_factory=notification_ids,
    )
    second_result = second_workflow.run(_rules(), TIMESTAMP)

    assert tuple(item.message for item in second_result.notifications) == (
        (
            "Product price decreased.\n"
            "Product: Parkside Test Tool\n"
            "Current price: 80.00 CZK\n"
            "Availability: available\n"
            f"URL: {PRODUCT_URL}"
        ),
        (
            "Product is back in stock.\n"
            "Product: Parkside Test Tool\n"
            "Current price: 80.00 CZK\n"
            "Availability: available\n"
            f"URL: {PRODUCT_URL}"
        ),
    )
    persisted = JsonStateStore(state_path).load(second_result.snapshots[0].product.id)
    assert persisted is not None
    assert persisted == second_result.snapshots[0]
    assert persisted.product.current_price.amount.as_tuple().exponent == -2
    assert persisted.product.availability
    assert output.getvalue().count("\n") == 10
