"""Deterministic operational health transitions."""

from dataclasses import replace
from datetime import datetime

from core.operations.enums import (
    OperationalHealthStatus,
    OperationalNotificationKind,
)
from core.operations.model import (
    DailyDigestDelivery,
    OperationalCheck,
    OperationalNotification,
    OperationalState,
)


class OperationalHealthEngine:
    """Transition durable operational state without side effects."""

    def evaluate(
        self,
        previous: OperationalState,
        check: OperationalCheck,
        failure_threshold: int = 3,
    ) -> OperationalState:
        """Apply one chronological check to the previous state."""
        _validate_state(previous)
        if not isinstance(check, OperationalCheck):
            raise TypeError("check must be an OperationalCheck")
        _validate_threshold(failure_threshold)
        if (
            previous.last_checked_at is not None
            and check.timestamp < previous.last_checked_at
        ):
            raise ValueError("check timestamp cannot precede previous check")
        if check.failure_kind is None:
            return _healthy_state(previous, check)
        return _failed_state(previous, check, failure_threshold)

    def record_digest_delivery(
        self,
        state: OperationalState,
        delivery: DailyDigestDelivery,
    ) -> OperationalState:
        """Retain the newest successful daily-digest delivery."""
        _validate_state(state)
        if not isinstance(delivery, DailyDigestDelivery):
            raise TypeError("delivery must be a DailyDigestDelivery")
        previous = state.last_digest_delivery
        if previous is not None and delivery.delivered_at < previous.delivered_at:
            raise ValueError("digest delivery cannot precede retained delivery")
        return replace(state, last_digest_delivery=delivery)

    def pending_notification(
        self,
        state: OperationalState,
    ) -> OperationalNotification | None:
        """Build the deterministic pending transition notification."""
        _validate_state(state)
        if state.pending_notification is None:
            return None
        if state.pending_notification is OperationalNotificationKind.FAILURE:
            return OperationalNotification(
                OperationalNotificationKind.FAILURE,
                _failure_message(state),
                _required_timestamp(state.last_checked_at, "last_checked_at"),
            )
        return OperationalNotification(
            OperationalNotificationKind.RECOVERY,
            _recovery_message(state),
            _required_timestamp(state.last_recovered_at, "last_recovered_at"),
        )

    def acknowledge_notification(
        self,
        state: OperationalState,
        kind: OperationalNotificationKind,
    ) -> OperationalState:
        """Acknowledge exactly the transition currently pending."""
        _validate_state(state)
        if not isinstance(kind, OperationalNotificationKind):
            raise TypeError("kind must be an OperationalNotificationKind")
        if state.pending_notification is not kind:
            raise ValueError("kind must match the pending notification")
        if kind is OperationalNotificationKind.FAILURE:
            return replace(
                state,
                incident_notified=True,
                pending_notification=None,
            )
        return replace(
            state,
            incident_started_at=None,
            incident_notified=False,
            pending_notification=None,
        )


def _healthy_state(
    previous: OperationalState,
    check: OperationalCheck,
) -> OperationalState:
    recovered = previous.status is not OperationalHealthStatus.OK
    if previous.status is OperationalHealthStatus.FAILED and previous.incident_notified:
        return OperationalState(
            OperationalHealthStatus.OK,
            None,
            0,
            previous.incident_started_at,
            check.timestamp,
            check.timestamp,
            True,
            OperationalNotificationKind.RECOVERY,
            previous.last_digest_delivery,
        )
    return OperationalState(
        OperationalHealthStatus.OK,
        None,
        0,
        None,
        check.timestamp,
        check.timestamp if recovered else previous.last_recovered_at,
        False,
        None,
        previous.last_digest_delivery,
    )


def _failed_state(
    previous: OperationalState,
    check: OperationalCheck,
    failure_threshold: int,
) -> OperationalState:
    continuing = previous.status is not OperationalHealthStatus.OK
    count = previous.consecutive_failure_cycles + 1 if continuing else 1
    started_at = previous.incident_started_at if continuing else check.timestamp
    status = (
        OperationalHealthStatus.FAILED
        if count >= failure_threshold
        else OperationalHealthStatus.DEGRADED
    )
    incident_notified = previous.incident_notified if continuing else False
    pending = previous.pending_notification if continuing else None
    if status is OperationalHealthStatus.DEGRADED:
        incident_notified = False
        pending = None
    elif previous.status is not OperationalHealthStatus.FAILED:
        pending = OperationalNotificationKind.FAILURE
        incident_notified = False
    return OperationalState(
        status,
        check.failure_kind,
        count,
        started_at,
        check.timestamp,
        previous.last_recovered_at,
        incident_notified,
        pending,
        previous.last_digest_delivery,
    )


def _failure_message(state: OperationalState) -> str:
    failure = state.failure_kind
    if failure is None:
        raise ValueError("failed notification requires failure_kind")
    return (
        "Price Watch operational failure\n"
        f"Cause: {failure.value}\n"
        f"Consecutive failed cycles: {state.consecutive_failure_cycles}\n"
        "Incident started: "
        f"{_required_timestamp(state.incident_started_at, 'incident_started_at').isoformat()}\n"
        "Last checked: "
        f"{_required_timestamp(state.last_checked_at, 'last_checked_at').isoformat()}"
    )


def _recovery_message(state: OperationalState) -> str:
    return (
        "Price Watch operational recovery\n"
        "Incident started: "
        f"{_required_timestamp(state.incident_started_at, 'incident_started_at').isoformat()}\n"
        "Recovered at: "
        f"{_required_timestamp(state.last_recovered_at, 'last_recovered_at').isoformat()}"
    )


def _validate_state(state: object) -> None:
    if not isinstance(state, OperationalState):
        raise TypeError("state must be an OperationalState")


def _validate_threshold(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("failure_threshold must be an int")
    if value <= 0:
        raise ValueError("failure_threshold must be greater than zero")


def _required_timestamp(value: datetime | None, name: str) -> datetime:
    if value is None:
        raise ValueError(f"{name} is required")
    return value
