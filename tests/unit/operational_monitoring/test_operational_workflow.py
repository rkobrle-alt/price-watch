"""Tests for operational monitoring orchestration."""

import inspect
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest

import applications.operational_monitoring as workflow_api
from applications.operational_monitoring import (
    OperationalMonitoringResult,
    OperationalMonitoringWorkflow,
)
from core.operations import (
    DailyDigestDelivery,
    OperationalCheck,
    OperationalFailureKind,
    OperationalHealthEngine,
    OperationalNotification,
    OperationalNotificationError,
    OperationalNotificationKind,
    OperationalState,
)

NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)


@dataclass(slots=True)
class _Store:
    state: OperationalState = field(default_factory=OperationalState.initial)
    loads: int = 0
    saves: list[OperationalState] = field(default_factory=list)

    def load(self) -> OperationalState:
        self.loads += 1
        return self.state

    def save(self, state: OperationalState) -> None:
        self.saves.append(state)
        self.state = state


@dataclass(slots=True)
class _Channel:
    failure: OperationalNotificationError | None = None
    calls: list[OperationalNotification] = field(default_factory=list)

    def send(self, notification: OperationalNotification) -> None:
        self.calls.append(notification)
        if self.failure is not None:
            raise self.failure


def _workflow(
    store: _Store | None = None,
    channel: _Channel | None = None,
) -> tuple[OperationalMonitoringWorkflow, _Store, _Channel]:
    selected_store = store or _Store()
    selected_channel = channel or _Channel()
    return (
        OperationalMonitoringWorkflow(
            selected_store,
            OperationalHealthEngine(),
            selected_channel,
        ),
        selected_store,
        selected_channel,
    )


def test_public_api_is_explicit_and_documented() -> None:
    assert workflow_api.__all__ == [
        "OperationalMonitoringResult",
        "OperationalMonitoringWorkflow",
    ]
    assert inspect.getdoc(OperationalMonitoringResult)
    assert inspect.getdoc(OperationalMonitoringWorkflow)
    assert inspect.getdoc(OperationalMonitoringWorkflow.run)


def test_workflow_saves_digest_and_healthy_transition_without_delivery() -> None:
    workflow, store, channel = _workflow()
    delivery = DailyDigestDelivery(date(2026, 8, 14), NOW, 7, True)

    result = workflow.run(OperationalCheck(NOW), delivery)

    assert result == OperationalMonitoringResult(store.state)
    assert result.state.last_digest_delivery == delivery
    assert store.loads == 1
    assert store.saves == [result.state]
    assert channel.calls == []


def test_workflow_saves_before_notification_and_acknowledges_after_success() -> None:
    engine = OperationalHealthEngine()
    state = OperationalState.initial()
    for offset in (1, 2):
        state = engine.evaluate(
            state,
            OperationalCheck(
                NOW + timedelta(minutes=offset),
                OperationalFailureKind.PROVIDER_UNAVAILABLE,
            ),
        )
    store = _Store(state)
    workflow, _, channel = _workflow(store)

    result = workflow.run(
        OperationalCheck(
            NOW + timedelta(minutes=3),
            OperationalFailureKind.PROVIDER_UNAVAILABLE,
        )
    )

    assert result.notification_sent is OperationalNotificationKind.FAILURE
    assert result.notification_error is None
    assert len(store.saves) == 2
    assert store.saves[0].pending_notification is OperationalNotificationKind.FAILURE
    assert store.saves[1] == result.state
    assert result.state.incident_notified is True
    assert len(channel.calls) == 1


def test_delivery_failure_retains_pending_state_for_retry() -> None:
    engine = OperationalHealthEngine()
    state = OperationalState.initial()
    for offset in (1, 2):
        state = engine.evaluate(
            state,
            OperationalCheck(
                NOW + timedelta(minutes=offset),
                OperationalFailureKind.PROVIDER_FAILURE,
            ),
        )
    failure = OperationalNotificationError("offline")
    channel = _Channel(failure)
    workflow, store, _ = _workflow(_Store(state), channel)

    first = workflow.run(
        OperationalCheck(
            NOW + timedelta(minutes=3),
            OperationalFailureKind.PROVIDER_FAILURE,
        )
    )
    channel.failure = None
    retried = workflow.run(
        OperationalCheck(
            NOW + timedelta(minutes=4),
            OperationalFailureKind.PROVIDER_FAILURE,
        )
    )

    assert first.notification_error is failure
    assert first.notification_sent is None
    assert first.state.pending_notification is OperationalNotificationKind.FAILURE
    assert retried.notification_sent is OperationalNotificationKind.FAILURE
    assert retried.state.incident_notified is True
    assert len(store.saves) == 3
    assert len(channel.calls) == 2


def test_result_and_workflow_reject_invalid_arguments() -> None:
    state = OperationalState.initial()
    with pytest.raises(TypeError, match="state"):
        OperationalMonitoringResult(cast(OperationalState, object()))
    with pytest.raises(TypeError, match="notification_sent"):
        OperationalMonitoringResult(state, cast(OperationalNotificationKind, "x"))
    with pytest.raises(TypeError, match="notification_error"):
        OperationalMonitoringResult(
            state,
            notification_error=cast(OperationalNotificationError, ValueError()),
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        OperationalMonitoringResult(
            state,
            OperationalNotificationKind.FAILURE,
            OperationalNotificationError("x"),
        )
    for arguments, name in (
        ((object(), OperationalHealthEngine(), _Channel()), "state_store"),
        ((_Store(), object(), _Channel()), "engine"),
        ((_Store(), OperationalHealthEngine(), object()), "notification_channel"),
    ):
        with pytest.raises(TypeError, match=name):
            OperationalMonitoringWorkflow(*cast(tuple, arguments))
    workflow, _, _ = _workflow()
    with pytest.raises(TypeError, match="check"):
        workflow.run(cast(OperationalCheck, object()))
    with pytest.raises(TypeError, match="digest_delivery"):
        workflow.run(OperationalCheck(NOW), cast(DailyDigestDelivery, object()))
