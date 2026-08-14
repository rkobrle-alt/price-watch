"""Tests for deterministic operational health contracts."""

import inspect
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest

import core.operations as operations_api
from core.operations import (
    DailyDigestDelivery,
    OperationalCheck,
    OperationalFailureKind,
    OperationalHealthEngine,
    OperationalHealthStatus,
    OperationalNotification,
    OperationalNotificationChannel,
    OperationalNotificationError,
    OperationalNotificationKind,
    OperationalState,
    OperationalStateError,
    OperationalStateStore,
)

NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)


class _Store:
    def load(self) -> OperationalState:
        return OperationalState.initial()

    def save(self, state: OperationalState) -> None:
        assert isinstance(state, OperationalState)


class _Channel:
    def send(self, notification: OperationalNotification) -> None:
        assert isinstance(notification, OperationalNotification)


def _fail(
    engine: OperationalHealthEngine,
    state: OperationalState,
    offset: int,
    kind: OperationalFailureKind = OperationalFailureKind.PROVIDER_UNAVAILABLE,
) -> OperationalState:
    return engine.evaluate(state, OperationalCheck(NOW + timedelta(minutes=offset), kind))


def test_public_api_is_explicit_documented_and_protocol_compatible() -> None:
    assert operations_api.__all__ == [
        "DailyDigestDelivery",
        "OperationalCheck",
        "OperationalFailureKind",
        "OperationalHealthEngine",
        "OperationalHealthStatus",
        "OperationalNotification",
        "OperationalNotificationChannel",
        "OperationalNotificationError",
        "OperationalNotificationKind",
        "OperationalState",
        "OperationalStateError",
        "OperationalStateStore",
    ]
    store: OperationalStateStore = _Store()
    channel: OperationalNotificationChannel = _Channel()
    channel.send(OperationalNotification(OperationalNotificationKind.FAILURE, "x", NOW))
    assert store.load() == OperationalState.initial()
    assert isinstance(OperationalStateError("state"), Exception)
    assert isinstance(OperationalNotificationError("notification"), Exception)
    for public in (
        DailyDigestDelivery,
        OperationalCheck,
        OperationalFailureKind,
        OperationalHealthEngine,
        OperationalHealthStatus,
        OperationalNotification,
        OperationalNotificationChannel,
        OperationalNotificationError,
        OperationalNotificationKind,
        OperationalState,
        OperationalStateError,
        OperationalStateStore,
    ):
        assert inspect.getdoc(public)


def test_initial_state_and_values_are_immutable() -> None:
    state = OperationalState.initial()

    assert state == OperationalState(
        OperationalHealthStatus.OK,
        None,
        0,
        None,
        None,
        None,
        False,
        None,
        None,
    )
    with pytest.raises(FrozenInstanceError):
        state.status = OperationalHealthStatus.FAILED  # type: ignore[misc]


def test_engine_transitions_degraded_failed_notified_and_recovered() -> None:
    engine = OperationalHealthEngine()
    state = OperationalState.initial()

    first = _fail(engine, state, 1)
    second = _fail(
        engine,
        first,
        2,
        OperationalFailureKind.PARTIAL_PROVIDER_FAILURE,
    )
    failed = _fail(engine, second, 3)

    assert first.status is OperationalHealthStatus.DEGRADED
    assert first.consecutive_failure_cycles == 1
    assert second.consecutive_failure_cycles == 2
    assert second.failure_kind is OperationalFailureKind.PARTIAL_PROVIDER_FAILURE
    assert second.incident_started_at == NOW + timedelta(minutes=1)
    assert failed.status is OperationalHealthStatus.FAILED
    assert failed.pending_notification is OperationalNotificationKind.FAILURE
    notification = engine.pending_notification(failed)
    assert notification == OperationalNotification(
        OperationalNotificationKind.FAILURE,
        "Price Watch operational failure\n"
        "Cause: provider_unavailable\n"
        "Consecutive failed cycles: 3\n"
        "Incident started: 2026-08-14T08:01:00+00:00\n"
        "Last checked: 2026-08-14T08:03:00+00:00",
        NOW + timedelta(minutes=3),
    )

    acknowledged = engine.acknowledge_notification(
        failed,
        OperationalNotificationKind.FAILURE,
    )
    continued = _fail(engine, acknowledged, 4)
    recovered = engine.evaluate(continued, OperationalCheck(NOW + timedelta(minutes=5)))

    assert continued.status is OperationalHealthStatus.FAILED
    assert continued.pending_notification is None
    assert continued.incident_notified is True
    assert recovered.status is OperationalHealthStatus.OK
    assert recovered.pending_notification is OperationalNotificationKind.RECOVERY
    recovery = engine.pending_notification(recovered)
    assert recovery == OperationalNotification(
        OperationalNotificationKind.RECOVERY,
        "Price Watch operational recovery\n"
        "Incident started: 2026-08-14T08:01:00+00:00\n"
        "Recovered at: 2026-08-14T08:05:00+00:00",
        NOW + timedelta(minutes=5),
    )
    final = engine.acknowledge_notification(
        recovered,
        OperationalNotificationKind.RECOVERY,
    )
    assert final.incident_started_at is None
    assert final.incident_notified is False
    assert final.pending_notification is None
    assert engine.pending_notification(final) is None


def test_recovery_without_acknowledged_incident_sends_nothing() -> None:
    engine = OperationalHealthEngine()
    state = OperationalState.initial()
    for offset in (1, 2, 3):
        state = _fail(engine, state, offset)

    recovered = engine.evaluate(state, OperationalCheck(NOW + timedelta(minutes=4)))

    assert recovered.status is OperationalHealthStatus.OK
    assert recovered.pending_notification is None
    assert recovered.last_recovered_at == NOW + timedelta(minutes=4)


def test_healthy_checks_preserve_last_recovery_and_digest() -> None:
    engine = OperationalHealthEngine()
    delivery = DailyDigestDelivery(date(2026, 8, 14), NOW, 4, True)
    state = engine.record_digest_delivery(OperationalState.initial(), delivery)
    healthy = engine.evaluate(state, OperationalCheck(NOW + timedelta(minutes=1)))
    healthy_again = engine.evaluate(
        replace(healthy, last_recovered_at=NOW),
        OperationalCheck(NOW + timedelta(minutes=2)),
    )

    assert healthy.last_digest_delivery == delivery
    assert healthy_again.last_recovered_at == NOW


def test_custom_threshold_and_digest_chronology_are_enforced() -> None:
    engine = OperationalHealthEngine()
    failed = engine.evaluate(
        OperationalState.initial(),
        OperationalCheck(NOW, OperationalFailureKind.PROVIDER_FAILURE),
        failure_threshold=1,
    )
    delivery = DailyDigestDelivery(date(2026, 8, 14), NOW, 0, False)
    retained = engine.record_digest_delivery(failed, delivery)

    assert failed.status is OperationalHealthStatus.FAILED
    assert retained.last_digest_delivery == delivery
    with pytest.raises(ValueError, match="precede"):
        engine.record_digest_delivery(
            retained,
            DailyDigestDelivery(
                date(2026, 8, 13),
                NOW - timedelta(seconds=1),
                1,
                False,
            ),
        )


@pytest.mark.parametrize("value", [True, 0, -1, "3"])
def test_engine_rejects_invalid_threshold(value: object) -> None:
    error = TypeError if value in (True, "3") else ValueError
    with pytest.raises(error):
        OperationalHealthEngine().evaluate(
            OperationalState.initial(),
            OperationalCheck(NOW),
            cast(int, value),
        )


def test_engine_rejects_invalid_arguments_and_chronology() -> None:
    engine = OperationalHealthEngine()
    state = engine.evaluate(OperationalState.initial(), OperationalCheck(NOW))

    with pytest.raises(TypeError, match="state"):
        engine.evaluate(cast(OperationalState, object()), OperationalCheck(NOW))
    with pytest.raises(TypeError, match="check"):
        engine.evaluate(state, cast(OperationalCheck, object()))
    with pytest.raises(ValueError, match="precede"):
        engine.evaluate(state, OperationalCheck(NOW - timedelta(seconds=1)))
    with pytest.raises(TypeError, match="delivery"):
        engine.record_digest_delivery(state, cast(DailyDigestDelivery, object()))
    with pytest.raises(TypeError, match="kind"):
        engine.acknowledge_notification(
            state,
            cast(OperationalNotificationKind, "failure"),
        )
    with pytest.raises(ValueError, match="pending"):
        engine.acknowledge_notification(state, OperationalNotificationKind.FAILURE)


@pytest.mark.parametrize(
    ("factory", "error"),
    [
        (lambda: OperationalCheck("now"), TypeError),
        (lambda: OperationalCheck(datetime(2026, 1, 1)), ValueError),
        (lambda: OperationalCheck(NOW, "failure"), TypeError),
        (lambda: DailyDigestDelivery(datetime(2026, 1, 1), NOW, 0, False), TypeError),
        (lambda: DailyDigestDelivery(date.today(), datetime(2026, 1, 1), 0, False), ValueError),
        (lambda: DailyDigestDelivery(date.today(), NOW, True, False), TypeError),
        (lambda: DailyDigestDelivery(date.today(), NOW, -1, False), ValueError),
        (lambda: DailyDigestDelivery(date.today(), NOW, 0, 1), TypeError),
        (lambda: OperationalNotification("failure", "x", NOW), TypeError),
        (lambda: OperationalNotification(OperationalNotificationKind.FAILURE, 1, NOW), TypeError),
        (lambda: OperationalNotification(OperationalNotificationKind.FAILURE, " ", NOW), ValueError),
        (lambda: OperationalNotification(OperationalNotificationKind.FAILURE, "x", datetime(2026, 1, 1)), ValueError),
    ],
)
def test_public_values_reject_invalid_arguments(factory: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        cast(object, factory)()


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "ok"},
        {"failure_kind": "provider_failure"},
        {"consecutive_failure_cycles": True},
        {"incident_started_at": "now"},
        {"last_checked_at": "now"},
        {"last_recovered_at": "now"},
        {"incident_notified": 1},
        {"pending_notification": "failure"},
        {"last_digest_delivery": object()},
        {"status": OperationalHealthStatus.OK, "failure_kind": OperationalFailureKind.PROVIDER_FAILURE},
        {"status": OperationalHealthStatus.DEGRADED, "incident_started_at": None},
        {"status": OperationalHealthStatus.DEGRADED, "incident_notified": True},
    ],
)
def test_operational_state_rejects_invalid_invariants(changes: dict[str, object]) -> None:
    base = OperationalState(
        OperationalHealthStatus.DEGRADED,
        OperationalFailureKind.PROVIDER_FAILURE,
        1,
        NOW,
        NOW,
        None,
        False,
        None,
        None,
    )
    with pytest.raises((TypeError, ValueError)):
        replace(base, **changes)


def test_operational_state_rejects_notification_and_chronology_invariants() -> None:
    with pytest.raises(ValueError, match="pending failure"):
        OperationalState(
            OperationalHealthStatus.FAILED,
            OperationalFailureKind.PROVIDER_FAILURE,
            3,
            NOW,
            NOW,
            None,
            True,
            OperationalNotificationKind.FAILURE,
            None,
        )
    with pytest.raises(ValueError, match="pending recovery"):
        replace(
            OperationalState.initial(),
            pending_notification=OperationalNotificationKind.RECOVERY,
        )
    with pytest.raises(ValueError, match="ok incident"):
        replace(OperationalState.initial(), incident_started_at=NOW)
    with pytest.raises(ValueError, match="incident_started_at"):
        OperationalState(
            OperationalHealthStatus.DEGRADED,
            OperationalFailureKind.PROVIDER_FAILURE,
            1,
            NOW + timedelta(seconds=1),
            NOW,
            None,
            False,
            None,
            None,
        )
    with pytest.raises(ValueError, match="last_recovered_at"):
        replace(
            OperationalState.initial(),
            last_checked_at=NOW,
            last_recovered_at=NOW + timedelta(seconds=1),
        )


def test_notification_builder_rejects_corrupted_required_state() -> None:
    engine = OperationalHealthEngine()
    state = OperationalState(
        OperationalHealthStatus.FAILED,
        OperationalFailureKind.PROVIDER_FAILURE,
        3,
        NOW,
        NOW,
        None,
        False,
        OperationalNotificationKind.FAILURE,
        None,
    )
    object.__setattr__(state, "failure_kind", None)
    with pytest.raises(ValueError, match="failure_kind"):
        engine.pending_notification(state)

    recovered = OperationalState(
        OperationalHealthStatus.OK,
        None,
        0,
        NOW,
        NOW,
        NOW,
        True,
        OperationalNotificationKind.RECOVERY,
        None,
    )
    object.__setattr__(recovered, "last_recovered_at", None)
    with pytest.raises(ValueError, match="last_recovered_at"):
        engine.pending_notification(recovered)
