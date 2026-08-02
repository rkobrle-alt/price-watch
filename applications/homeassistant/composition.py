"""Concrete Home Assistant workflow composition."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from applications.homeassistant.configuration import HomeAssistantConfig
from applications.synchronization import SynchronizationWorkflow
from applications.version import VERSION
from core.domain import Rule, RuleType
from core.notifications import NotificationEngine
from core.rules import EvaluatorRegistry, RuleEngine
from core.rules.evaluators import BackInStockEvaluator, PriceDropEvaluator
from infrastructure.homeassistant import UrllibHomeAssistantClient
from infrastructure.http import UrllibTextHttpClient
from infrastructure.notifications.homeassistant import (
    HomeAssistantNotificationChannel,
)
from infrastructure.persistence.json import JsonStateStore
from infrastructure.providers.lidl import LidlParksideProvider

_SUPERVISOR_CORE_API = "http://supervisor/core/api"
_PRICE_DROP_RULE_ID = UUID("70000000-0000-4000-8000-000000000001")
_BACK_IN_STOCK_RULE_ID = UUID("70000000-0000-4000-8000-000000000002")


@dataclass(frozen=True, slots=True)
class _HomeAssistantComposition:
    """Hold a composed workflow, rules and required interval."""

    workflow: SynchronizationWorkflow
    rules: tuple[Rule, ...]
    interval: timedelta


def _compose_homeassistant(
    config: HomeAssistantConfig,
    access_token: str,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
) -> _HomeAssistantComposition:
    """Compose the concrete Supervisor-hosted monitoring stack."""
    if not isinstance(config, HomeAssistantConfig):
        raise TypeError("config must be a HomeAssistantConfig")
    if not isinstance(access_token, str):
        raise TypeError("access_token must be a string")
    if not access_token.strip():
        raise ValueError("access_token cannot be blank")
    if not callable(clock):
        raise TypeError("clock must be callable")
    if not callable(notification_id_factory):
        raise TypeError("notification_id_factory must be callable")

    application = config.application
    interval = application.interval
    if interval is None:
        raise ValueError("application interval is required")
    provider = LidlParksideProvider(
        application.product_urls,
        UrllibTextHttpClient(
            timeout_seconds=application.timeout_seconds,
            user_agent=f"PriceWatch/{VERSION}",
        ),
        clock,
    )
    homeassistant_client = UrllibHomeAssistantClient(
        _SUPERVISOR_CORE_API,
        access_token,
        timeout_seconds=application.timeout_seconds,
        user_agent=f"PriceWatch/{VERSION}",
    )
    registry = EvaluatorRegistry()
    registry.register(PriceDropEvaluator())
    registry.register(BackInStockEvaluator())
    rules = _create_rules(
        application.price_drop_percentage,
        application.price_drop_amount,
    )
    workflow = SynchronizationWorkflow(
        providers=(provider,),
        state_store=JsonStateStore(application.state_file),
        rule_engine=RuleEngine(registry),
        notification_engine=NotificationEngine(),
        notification_channel=HomeAssistantNotificationChannel(
            homeassistant_client,
            config.notify_entity,
            config.notification_title,
        ),
        notification_id_factory=notification_id_factory,
    )
    return _HomeAssistantComposition(workflow, rules, interval)


def _create_rules(
    percentage: Decimal | None,
    amount: Decimal | None,
) -> tuple[Rule, ...]:
    parameters: dict[str, Decimal] = {}
    if percentage is not None:
        parameters["percentage"] = percentage
    if amount is not None:
        parameters["fixed_amount"] = amount
    return (
        Rule(
            id=_PRICE_DROP_RULE_ID,
            name="Price Watch price drop",
            enabled=True,
            rule_type=RuleType.PRICE_DROP,
            parameters=parameters,
        ),
        Rule(
            id=_BACK_IN_STOCK_RULE_ID,
            name="Price Watch back in stock",
            enabled=True,
            rule_type=RuleType.BACK_IN_STOCK,
        ),
    )
