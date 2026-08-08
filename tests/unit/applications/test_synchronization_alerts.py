"""Tests for optional historical price alerts in synchronization."""

from dataclasses import dataclass, field, replace
from typing import cast

import pytest

from applications.synchronization import SynchronizationWorkflow
from core.domain import Product, Rule
from core.notifications import (
    NotificationChannel,
    NotificationEngine,
    NotificationReservation,
    NotificationReservationStore,
    PriceDropReservationPolicy,
)
from core.provider import Provider
from core.rules import PriceReferencePolicy, RuleEngine
from core.state import ObservationHistory, StateSnapshot, StateStore
from tests.unit.applications.helpers import (
    PREVIOUS_TIMESTAMP,
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


@dataclass
class _History:
    snapshots: tuple[StateSnapshot, ...]
    events: list[str] = field(default_factory=list)
    result: object | None = None

    def history(
        self,
        product_id: object,
        limit: int | None = None,
    ) -> tuple[StateSnapshot, ...]:
        self.events.append("history")
        if self.result is not None:
            return cast(tuple[StateSnapshot, ...], self.result)
        return self.snapshots


@dataclass
class _Reservations:
    values: set[NotificationReservation] = field(default_factory=set)
    events: list[str] = field(default_factory=list)
    result: object | None = None

    def reserve(
        self,
        reservation: NotificationReservation,
        reserved_at: object,
    ) -> bool:
        self.events.append("reserve")
        if self.result is not None:
            return cast(bool, self.result)
        if reservation in self.values:
            return False
        self.values.add(reservation)
        return True

    def release(self, reservation: NotificationReservation) -> None:
        self.events.append("release")
        self.values.discard(reservation)


class _BadReferencePolicy:
    def enrich(self, current: Product, history: object) -> object:
        return object()


class _BadReservationPolicy:
    def create(self, rule: Rule, product: Product, evaluation: object) -> object:
        return object()


class _AlwaysReservationPolicy:
    def create(
        self,
        rule: Rule,
        product: Product,
        evaluation: object,
    ) -> NotificationReservation:
        return NotificationReservation(
            product.id,
            rule.rule_type,
            product.current_price,
        )


def _workflow(
    *,
    current: Product | None = None,
    state_store: RecordingStateStore | None = None,
    history: object | None = None,
    reference_policy: object | None = None,
    reservations: object | None = None,
    reservation_policy: object | None = None,
    notification_engine: RecordingNotificationEngine | None = None,
    channel: RecordingChannel | None = None,
) -> SynchronizationWorkflow:
    events: list[str] = []
    product = create_product(amount="80") if current is None else current
    return SynchronizationWorkflow(
        providers=cast(
            tuple[Provider, ...],
            (RecordingProvider("catalog", events, create_fetch_result((product,))),),
        ),
        state_store=cast(
            StateStore,
            RecordingStateStore(events) if state_store is None else state_store,
        ),
        rule_engine=cast(RuleEngine, RecordingRuleEngine(events)),
        notification_engine=cast(
            NotificationEngine,
            RecordingNotificationEngine(events)
            if notification_engine is None
            else notification_engine,
        ),
        notification_channel=cast(
            NotificationChannel,
            RecordingChannel(events) if channel is None else channel,
        ),
        notification_id_factory=RecordingIdFactory(events),
        observation_history=cast(ObservationHistory | None, history),
        price_reference_policy=cast(
            PriceReferencePolicy | None,
            reference_policy,
        ),
        notification_reservation_store=cast(
            NotificationReservationStore | None,
            reservations,
        ),
        price_drop_reservation_policy=cast(
            PriceDropReservationPolicy | None,
            reservation_policy,
        ),
    )


def _alert_dependencies(
    product: Product,
) -> tuple[_History, _Reservations]:
    previous = create_product(amount="100")
    previous = replace(previous, id=product.id)
    history = _History((StateSnapshot(previous, PREVIOUS_TIMESTAMP),))
    return history, _Reservations()


def test_history_enrichment_and_reservation_suppress_equal_repeat() -> None:
    product = create_product(amount="80")
    history, reservations = _alert_dependencies(product)
    first = _workflow(
        current=product,
        history=history,
        reference_policy=PriceReferencePolicy(),
        reservations=reservations,
        reservation_policy=PriceDropReservationPolicy(),
    ).run((create_rule(),), TIMESTAMP)
    second = _workflow(
        current=product,
        history=history,
        reference_policy=PriceReferencePolicy(),
        reservations=reservations,
        reservation_policy=PriceDropReservationPolicy(),
    ).run((create_rule(),), TIMESTAMP)

    assert first.snapshots[0].product.original_price is not None
    assert len(first.notifications) == 1
    assert first.suppressed_notification_count == 0
    assert second.notifications == ()
    assert second.suppressed_notification_count == 1
    assert history.events == ["history", "history"]


@pytest.mark.parametrize("failure_target", ["generation", "delivery"])
def test_failed_notification_releases_reservation(failure_target: str) -> None:
    product = create_product(amount="80")
    history, reservations = _alert_dependencies(product)
    engine = RecordingNotificationEngine([], RuntimeError("generation"))
    channel = RecordingChannel([], error=RuntimeError("delivery"))
    if failure_target == "generation":
        channel.error = None
    else:
        engine.error = None

    with pytest.raises(RuntimeError, match=failure_target):
        _workflow(
            current=product,
            history=history,
            reference_policy=PriceReferencePolicy(),
            reservations=reservations,
            reservation_policy=PriceDropReservationPolicy(),
            notification_engine=engine,
            channel=channel,
        ).run((create_rule(),), TIMESTAMP)

    assert reservations.values == set()
    assert reservations.events == ["reserve", "release"]


def test_snapshot_failure_retains_successful_reservation() -> None:
    product = create_product(amount="80")
    history, reservations = _alert_dependencies(product)
    store = RecordingStateStore([], save_error=RuntimeError("save"))

    with pytest.raises(RuntimeError, match="save"):
        _workflow(
            current=product,
            state_store=store,
            history=history,
            reference_policy=PriceReferencePolicy(),
            reservations=reservations,
            reservation_policy=PriceDropReservationPolicy(),
        ).run((create_rule(),), TIMESTAMP)

    assert len(reservations.values) == 1
    assert reservations.events == ["reserve"]


def test_none_generation_releases_unexpected_reservation() -> None:
    product = create_product(amount="80")
    history, reservations = _alert_dependencies(product)

    result = _workflow(
        current=product,
        history=history,
        reference_policy=PriceReferencePolicy(),
        reservations=reservations,
        reservation_policy=_AlwaysReservationPolicy(),
    ).run((create_rule("no-match"),), TIMESTAMP)

    assert result.notifications == ()
    assert reservations.events == ["reserve", "release"]


@pytest.mark.parametrize("invalid", [[], (object(),)])
def test_history_must_return_snapshot_tuple(invalid: object) -> None:
    product = create_product()
    history = _History((), result=invalid)

    with pytest.raises(TypeError, match="observation history"):
        _workflow(
            current=product,
            history=history,
            reference_policy=PriceReferencePolicy(),
        ).run((), TIMESTAMP)


def test_reference_policy_must_return_product() -> None:
    with pytest.raises(TypeError, match="must return a Product"):
        _workflow(
            history=_History(()),
            reference_policy=_BadReferencePolicy(),
        ).run((), TIMESTAMP)


def test_reservation_policy_must_return_reservation() -> None:
    with pytest.raises(TypeError, match="must return"):
        _workflow(
            reservations=_Reservations(),
            reservation_policy=_BadReservationPolicy(),
        ).run((create_rule(),), TIMESTAMP)


def test_reservation_store_must_return_bool() -> None:
    with pytest.raises(TypeError, match="must return a bool"):
        _workflow(
            reservations=_Reservations(result="yes"),
            reservation_policy=PriceDropReservationPolicy(),
        ).run((create_rule(),), TIMESTAMP)


@pytest.mark.parametrize(
    ("history", "policy", "reservations", "reservation_policy", "error"),
    [
        (_History(()), None, None, None, ValueError),
        (None, PriceReferencePolicy(), None, None, ValueError),
        (object(), PriceReferencePolicy(), None, None, TypeError),
        (_History(()), object(), None, None, TypeError),
        (None, None, _Reservations(), None, ValueError),
        (None, None, None, PriceDropReservationPolicy(), ValueError),
        (None, None, object(), PriceDropReservationPolicy(), TypeError),
        (None, None, _Reservations(), object(), TypeError),
    ],
)
def test_optional_collaborators_are_validated_in_pairs(
    history: object | None,
    policy: object | None,
    reservations: object | None,
    reservation_policy: object | None,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        _workflow(
            history=history,
            reference_policy=policy,
            reservations=reservations,
            reservation_policy=reservation_policy,
        )
