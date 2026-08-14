"""Operational state persistence and notification orchestration."""

from typing import cast

from applications.operational_monitoring.result import OperationalMonitoringResult
from core.operations import (
    DailyDigestDelivery,
    OperationalCheck,
    OperationalHealthEngine,
    OperationalNotificationChannel,
    OperationalNotificationError,
    OperationalStateStore,
)


class OperationalMonitoringWorkflow:
    """Persist health transitions and retry pending notifications."""

    def __init__(
        self,
        state_store: OperationalStateStore,
        engine: OperationalHealthEngine,
        notification_channel: OperationalNotificationChannel,
    ) -> None:
        """Validate and retain injected collaborators."""
        _require_method(state_store, "load", "state_store")
        _require_method(state_store, "save", "state_store")
        if not isinstance(engine, OperationalHealthEngine):
            raise TypeError("engine must be an OperationalHealthEngine")
        _require_method(notification_channel, "send", "notification_channel")
        self._state_store = cast(OperationalStateStore, state_store)
        self._engine = engine
        self._notification_channel = cast(
            OperationalNotificationChannel,
            notification_channel,
        )

    def run(
        self,
        check: OperationalCheck,
        digest_delivery: DailyDigestDelivery | None = None,
    ) -> OperationalMonitoringResult:
        """Save one transition and deliver or retain its pending message."""
        if not isinstance(check, OperationalCheck):
            raise TypeError("check must be an OperationalCheck")
        if digest_delivery is not None and not isinstance(
            digest_delivery,
            DailyDigestDelivery,
        ):
            raise TypeError(
                "digest_delivery must be a DailyDigestDelivery or None"
            )
        state = self._state_store.load()
        if digest_delivery is not None:
            state = self._engine.record_digest_delivery(state, digest_delivery)
        state = self._engine.evaluate(state, check)
        self._state_store.save(state)
        notification = self._engine.pending_notification(state)
        if notification is None:
            return OperationalMonitoringResult(state)
        try:
            self._notification_channel.send(notification)
        except OperationalNotificationError as error:
            return OperationalMonitoringResult(
                state,
                notification_error=error,
            )
        acknowledged = self._engine.acknowledge_notification(
            state,
            notification.kind,
        )
        self._state_store.save(acknowledged)
        return OperationalMonitoringResult(
            acknowledged,
            notification_sent=notification.kind,
        )


def _require_method(value: object, method: str, name: str) -> None:
    if not callable(getattr(value, method, None)):
        raise TypeError(f"{name} must expose a callable {method} method")
