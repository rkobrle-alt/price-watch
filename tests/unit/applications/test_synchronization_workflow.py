"""Behavior tests for complete synchronization orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import pytest

from applications.synchronization import SynchronizationWorkflow
from core.domain import ProviderId, Rule
from core.notifications import NotificationChannel, NotificationEngine
from core.provider import FetchResult, Provider, ProviderError
from core.rules import RuleEngine
from core.state import StateSnapshot, StateStore
from tests.unit.applications.helpers import (
    PREVIOUS_TIMESTAMP,
    PROVIDER_ID,
    TIMESTAMP,
    RecordingChannel,
    RecordingIdFactory,
    RecordingNotificationEngine,
    RecordingProvider,
    RecordingRuleEngine,
    RecordingStateStore,
    create_fetch_result,
    create_product,
    create_rule,
)


def _create_workflow(
    events: list[str],
    *,
    providers: tuple[Provider, ...] | None = None,
    state_store: StateStore | None = None,
    rule_engine: RuleEngine | None = None,
    notification_engine: NotificationEngine | None = None,
    notification_channel: NotificationChannel | None = None,
    notification_id_factory: object | None = None,
) -> SynchronizationWorkflow:
    product = create_product()
    selected_providers = (
        cast(
            tuple[Provider, ...],
            (
                RecordingProvider(
                    "default",
                    events,
                    create_fetch_result((product,)),
                ),
            ),
        )
        if providers is None
        else providers
    )
    return SynchronizationWorkflow(
        providers=selected_providers,
        state_store=state_store or cast(StateStore, RecordingStateStore(events)),
        rule_engine=rule_engine or cast(RuleEngine, RecordingRuleEngine(events)),
        notification_engine=notification_engine
        or cast(NotificationEngine, RecordingNotificationEngine(events)),
        notification_channel=notification_channel
        or cast(NotificationChannel, RecordingChannel(events)),
        notification_id_factory=cast(
            Callable[[], UUID],
            notification_id_factory or RecordingIdFactory(events),
        ),
    )


@dataclass
class ProviderShape:
    """Mutable provider-shaped object used for constructor validation."""

    id: object = PROVIDER_ID
    display_name: object = "Provider"
    version: object = "1.0"
    fetch: object = create_fetch_result


@pytest.mark.parametrize(
    ("providers", "exception_type"),
    [
        (cast(tuple[Provider, ...], []), TypeError),
        ((), ValueError),
        ((object(),), TypeError),
        ((ProviderShape(id=object()),), TypeError),
        ((ProviderShape(display_name=1),), TypeError),
        ((ProviderShape(display_name=" "),), ValueError),
        ((ProviderShape(version=1),), TypeError),
        ((ProviderShape(version=" "),), ValueError),
        ((ProviderShape(fetch=None),), TypeError),
    ],
)
def test_constructor_rejects_invalid_provider_configuration(
    providers: object,
    exception_type: type[Exception],
) -> None:
    events: list[str] = []

    with pytest.raises(exception_type):
        _create_workflow(events, providers=cast(tuple[Provider, ...], providers))


@pytest.mark.parametrize(
    ("dependency_name", "invalid_dependency"),
    [
        ("state_store", object()),
        ("state_store", type("LoadOnly", (), {"load": lambda self, value: None})()),
        ("rule_engine", object()),
        ("notification_engine", object()),
        ("notification_channel", object()),
        ("notification_id_factory", 1),
    ],
)
def test_constructor_rejects_invalid_dependencies(
    dependency_name: str,
    invalid_dependency: object,
) -> None:
    events: list[str] = []
    arguments = {dependency_name: invalid_dependency}

    with pytest.raises(TypeError):
        _create_workflow(events, **arguments)


def test_construction_has_no_dependency_side_effects() -> None:
    events: list[str] = []

    _create_workflow(events)

    assert events == []


@pytest.mark.parametrize(
    ("rules", "timestamp", "exception_type"),
    [
        (cast(tuple[Rule, ...], []), TIMESTAMP, TypeError),
        ((object(),), TIMESTAMP, TypeError),
        ((), cast(datetime, object()), TypeError),
        ((), TIMESTAMP.replace(tzinfo=None), ValueError),
    ],
)
def test_run_rejects_invalid_arguments(
    rules: tuple[Rule, ...],
    timestamp: datetime,
    exception_type: type[Exception],
) -> None:
    workflow = _create_workflow([])

    with pytest.raises(exception_type):
        workflow.run(rules, timestamp)


def test_complete_product_flow_preserves_order_and_previous_state() -> None:
    events: list[str] = []
    current = create_product(amount="80")
    previous = create_product(amount="100")
    previous_snapshot = StateSnapshot(previous, PREVIOUS_TIMESTAMP)
    store = RecordingStateStore(events, {current.id: previous_snapshot})
    rules = (create_rule("match"), create_rule("no-match"))
    rule_engine = RecordingRuleEngine(events)
    channel = RecordingChannel(events)
    id_factory = RecordingIdFactory(events)
    provider = RecordingProvider(
        "lidl",
        events,
        create_fetch_result((current,)),
    )
    workflow = _create_workflow(
        events,
        providers=cast(tuple[Provider, ...], (provider,)),
        state_store=cast(StateStore, store),
        rule_engine=cast(RuleEngine, rule_engine),
        notification_channel=cast(NotificationChannel, channel),
        notification_id_factory=id_factory,
    )

    result = workflow.run(rules, TIMESTAMP)

    product_id = str(current.id.value)
    assert events == [
        "fetch:lidl",
        f"load:{product_id}",
        f"evaluate:match:{product_id}",
        "notification_id",
        f"generate:True:{product_id}",
        f"send:{product_id}",
        f"evaluate:no-match:{product_id}",
        "notification_id",
        f"generate:False:{product_id}",
        f"save:{product_id}",
    ]
    assert rule_engine.previous_products == [previous, previous]
    assert result.fetch_results == (provider.outcome,)
    assert tuple(evaluation.matched for evaluation in result.evaluations) == (
        True,
        False,
    )
    assert result.notifications == tuple(channel.sent)
    assert result.notifications[0].id != id_factory.values[0]
    assert result.snapshots == (StateSnapshot(current, TIMESTAMP),)
    assert result.provider_errors == ()
    assert store.values[current.id].timestamp == TIMESTAMP


def test_provider_errors_are_isolated_and_aggregated_in_provider_order() -> None:
    events: list[str] = []
    returned_error = ProviderError("partial failure")
    raised_error = ProviderError("provider unavailable")
    first_result = create_fetch_result(errors=(returned_error,))
    last_result = create_fetch_result()
    providers = cast(
        tuple[Provider, ...],
        (
            RecordingProvider("first", events, first_result),
            RecordingProvider("second", events, raised_error),
            RecordingProvider("third", events, last_result),
        ),
    )
    workflow = _create_workflow(events, providers=providers)

    result = workflow.run((), TIMESTAMP)

    assert events == ["fetch:first", "fetch:second", "fetch:third"]
    assert result.fetch_results == (first_result, last_result)
    assert result.provider_errors == (returned_error, raised_error)


def test_product_without_rules_is_still_saved() -> None:
    events: list[str] = []
    product = create_product()
    provider = RecordingProvider("provider", events, create_fetch_result((product,)))
    store = RecordingStateStore(events)
    workflow = _create_workflow(
        events,
        providers=cast(tuple[Provider, ...], (provider,)),
        state_store=cast(StateStore, store),
    )

    result = workflow.run((), TIMESTAMP)

    assert result.evaluations == ()
    assert result.notifications == ()
    assert result.snapshots == (StateSnapshot(product, TIMESTAMP),)
    assert store.values[product.id] == result.snapshots[0]


def test_invalid_provider_return_type_propagates_type_error() -> None:
    events: list[str] = []
    provider = RecordingProvider(
        "invalid",
        events,
        cast(FetchResult, object()),
    )
    workflow = _create_workflow(
        events,
        providers=cast(tuple[Provider, ...], (provider,)),
    )

    with pytest.raises(TypeError, match="FetchResult"):
        workflow.run((), TIMESTAMP)


def test_unexpected_provider_failure_stops_later_providers() -> None:
    events: list[str] = []
    failure = RuntimeError("unexpected")
    providers = cast(
        tuple[Provider, ...],
        (
            RecordingProvider("first", events, failure),
            RecordingProvider("second", events, create_fetch_result()),
        ),
    )
    workflow = _create_workflow(events, providers=providers)

    with pytest.raises(RuntimeError) as captured:
        workflow.run((), TIMESTAMP)

    assert captured.value is failure
    assert events == ["fetch:first"]


@pytest.mark.parametrize(
    "failure_stage",
    ["load", "rule", "identifier", "generation"],
)
def test_pre_delivery_failures_propagate_without_saving(
    failure_stage: str,
) -> None:
    events: list[str] = []
    failure = RuntimeError(f"{failure_stage} failed")
    store = RecordingStateStore(
        events,
        load_error=failure if failure_stage == "load" else None,
    )
    rule_engine = RecordingRuleEngine(
        events,
        error=failure if failure_stage == "rule" else None,
    )
    notification_engine = RecordingNotificationEngine(
        events,
        error=failure if failure_stage == "generation" else None,
    )
    id_factory = RecordingIdFactory(
        events,
        error=failure if failure_stage == "identifier" else None,
    )
    workflow = _create_workflow(
        events,
        state_store=cast(StateStore, store),
        rule_engine=cast(RuleEngine, rule_engine),
        notification_engine=cast(NotificationEngine, notification_engine),
        notification_id_factory=id_factory,
    )

    with pytest.raises(RuntimeError) as captured:
        workflow.run((create_rule(),), TIMESTAMP)

    assert captured.value is failure
    assert not any(event.startswith("save:") for event in events)


def test_delivery_failure_prevents_snapshot_save() -> None:
    events: list[str] = []
    failure = RuntimeError("delivery failed")
    channel = RecordingChannel(events, error=failure)
    workflow = _create_workflow(
        events,
        notification_channel=cast(NotificationChannel, channel),
    )

    with pytest.raises(RuntimeError) as captured:
        workflow.run((create_rule(),), TIMESTAMP)

    assert captured.value is failure
    assert any(event.startswith("send:") for event in events)
    assert not any(event.startswith("save:") for event in events)


def test_save_failure_occurs_after_delivery_and_propagates() -> None:
    events: list[str] = []
    failure = RuntimeError("save failed")
    store = RecordingStateStore(events, save_error=failure)
    channel = RecordingChannel(events)
    workflow = _create_workflow(
        events,
        state_store=cast(StateStore, store),
        notification_channel=cast(NotificationChannel, channel),
    )

    with pytest.raises(RuntimeError) as captured:
        workflow.run((create_rule(),), TIMESTAMP)

    assert captured.value is failure
    send_index = next(i for i, event in enumerate(events) if event.startswith("send:"))
    save_index = next(i for i, event in enumerate(events) if event.startswith("save:"))
    assert send_index < save_index
    assert len(channel.sent) == 1
