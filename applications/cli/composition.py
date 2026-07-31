"""Concrete dependency composition for CLI synchronization."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TextIO
from uuid import UUID

from applications.cli.arguments import SyncArguments
from applications.cli.version import VERSION
from applications.synchronization import SynchronizationWorkflow
from core.domain import Rule, RuleType
from core.notifications import NotificationEngine
from core.rules import EvaluatorRegistry, RuleEngine
from core.rules.evaluators import BackInStockEvaluator, PriceDropEvaluator
from infrastructure.http import UrllibTextHttpClient
from infrastructure.notifications.console import ConsoleNotificationChannel
from infrastructure.persistence.json import JsonStateStore
from infrastructure.providers.lidl import LidlParksideProvider

PRICE_DROP_RULE_ID = UUID("70000000-0000-4000-8000-000000000001")
BACK_IN_STOCK_RULE_ID = UUID("70000000-0000-4000-8000-000000000002")


@dataclass(frozen=True, slots=True)
class SyncComposition:
    """Hold a fully composed workflow and its immutable built-in rules."""

    workflow: SynchronizationWorkflow
    rules: tuple[Rule, ...]

    def __post_init__(self) -> None:
        """Validate composition result types."""
        if not isinstance(self.workflow, SynchronizationWorkflow):
            raise TypeError("workflow must be a SynchronizationWorkflow")
        if not isinstance(self.rules, tuple) or not all(
            isinstance(rule, Rule) for rule in self.rules
        ):
            raise TypeError("rules must be a tuple of Rule instances")


def compose_sync(
    arguments: SyncArguments,
    stdout: TextIO,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
) -> SyncComposition:
    """Compose the approved concrete stack for one CLI sync command."""
    if not isinstance(arguments, SyncArguments):
        raise TypeError("arguments must be SyncArguments")
    http_client = UrllibTextHttpClient(
        timeout_seconds=arguments.timeout_seconds,
        user_agent=f"PriceWatch/{VERSION}",
    )
    provider = LidlParksideProvider(
        arguments.product_urls,
        http_client,
        clock,
    )
    registry = EvaluatorRegistry()
    registry.register(PriceDropEvaluator())
    registry.register(BackInStockEvaluator())
    rules = _create_rules(arguments)
    workflow = SynchronizationWorkflow(
        providers=(provider,),
        state_store=JsonStateStore(arguments.state_file),
        rule_engine=RuleEngine(registry),
        notification_engine=NotificationEngine(),
        notification_channel=ConsoleNotificationChannel(stdout),
        notification_id_factory=notification_id_factory,
    )
    return SyncComposition(workflow=workflow, rules=rules)


def _create_rules(arguments: SyncArguments) -> tuple[Rule, ...]:
    parameters: dict[str, Decimal] = {}
    if arguments.price_drop_percentage is not None:
        parameters["percentage"] = arguments.price_drop_percentage
    if arguments.price_drop_amount is not None:
        parameters["fixed_amount"] = arguments.price_drop_amount
    return (
        Rule(
            id=PRICE_DROP_RULE_ID,
            name="CLI price drop",
            enabled=True,
            rule_type=RuleType.PRICE_DROP,
            parameters=parameters,
        ),
        Rule(
            id=BACK_IN_STOCK_RULE_ID,
            name="CLI back in stock",
            enabled=True,
            rule_type=RuleType.BACK_IN_STOCK,
        ),
    )
