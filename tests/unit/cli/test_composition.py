"""Tests for concrete CLI dependency composition."""

from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from applications.cli.arguments import SyncArguments
from applications.cli.composition import (
    BACK_IN_STOCK_RULE_ID,
    PRICE_DROP_RULE_ID,
    SyncComposition,
    compose_sync,
)
from applications.cli.version import VERSION
from applications.synchronization import SynchronizationWorkflow
from core.domain import Rule, RuleType
from core.rules.evaluators import BackInStockEvaluator, PriceDropEvaluator
from infrastructure.http import UrllibTextHttpClient
from infrastructure.notifications.console import ConsoleNotificationChannel
from infrastructure.persistence.json import JsonStateStore
from infrastructure.providers.lidl import LidlParksideProvider
from tests.unit.cli.helpers import (
    RecordingStream,
    fixed_clock,
    fixed_notification_id,
)


def _arguments(
    *,
    percentage: Decimal | None = None,
    amount: Decimal | None = None,
) -> SyncArguments:
    return SyncArguments(
        product_urls=("https://www.lidl.cz/tool/p100",),
        state_file=Path("data/state.json"),
        timeout_seconds=15,
        price_drop_percentage=percentage,
        price_drop_amount=amount,
    )


def test_compose_sync_builds_exact_approved_stack_and_rule_order() -> None:
    stdout = RecordingStream()
    composition = compose_sync(
        _arguments(
            percentage=Decimal("12.50"),
            amount=Decimal("200.00"),
        ),
        stdout,
        fixed_clock,
        fixed_notification_id,
    )
    workflow = composition.workflow
    provider = workflow._providers[0]

    assert isinstance(provider, LidlParksideProvider)
    assert provider._product_urls == ("https://www.lidl.cz/tool/p100",)
    assert provider._clock is fixed_clock
    assert isinstance(provider._http_client, UrllibTextHttpClient)
    assert provider._http_client._timeout_seconds == 15
    assert provider._http_client._user_agent == f"PriceWatch/{VERSION}"
    assert isinstance(workflow._state_store, JsonStateStore)
    assert workflow._state_store._path == Path("data/state.json")
    assert tuple(
        type(evaluator) for evaluator in workflow._rule_engine._registry.list()
    ) == (PriceDropEvaluator, BackInStockEvaluator)
    assert isinstance(workflow._notification_channel, ConsoleNotificationChannel)
    assert workflow._notification_channel._stream is stdout
    assert workflow._notification_id_factory is fixed_notification_id
    assert tuple(rule.rule_type for rule in composition.rules) == (
        RuleType.PRICE_DROP,
        RuleType.BACK_IN_STOCK,
    )
    assert tuple(rule.id for rule in composition.rules) == (
        PRICE_DROP_RULE_ID,
        BACK_IN_STOCK_RULE_ID,
    )
    assert composition.rules[0].parameters == {
        "percentage": Decimal("12.50"),
        "fixed_amount": Decimal("200.00"),
    }
    assert composition.rules[1].parameters == {}
    assert all(rule.enabled for rule in composition.rules)


def test_compose_sync_omits_unconfigured_price_thresholds() -> None:
    composition = compose_sync(
        _arguments(),
        RecordingStream(),
        fixed_clock,
        fixed_notification_id,
    )

    assert composition.rules[0].parameters == {}


def test_compose_sync_rejects_invalid_argument_object() -> None:
    with pytest.raises(TypeError):
        compose_sync(
            cast(SyncArguments, object()),
            RecordingStream(),
            fixed_clock,
            fixed_notification_id,
        )


def test_compose_sync_delegates_invalid_url_validation() -> None:
    arguments = SyncArguments(
        product_urls=("https://example.test/tool/p100",),
        state_file=Path("state.json"),
    )

    with pytest.raises(ValueError, match="Lidl"):
        compose_sync(
            arguments,
            RecordingStream(),
            fixed_clock,
            fixed_notification_id,
        )


def test_sync_composition_validates_public_fields() -> None:
    valid = compose_sync(
        _arguments(),
        RecordingStream(),
        fixed_clock,
        fixed_notification_id,
    )

    with pytest.raises(TypeError, match="workflow"):
        SyncComposition(cast(SynchronizationWorkflow, object()), valid.rules)
    with pytest.raises(TypeError, match="rules"):
        SyncComposition(valid.workflow, cast(tuple[Rule, ...], []))
    with pytest.raises(TypeError, match="rules"):
        SyncComposition(valid.workflow, (cast(Rule, object()),))
