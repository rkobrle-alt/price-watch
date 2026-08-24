"""Weekly operational aggregation and delivery orchestration."""

from datetime import date, datetime, time, timedelta
from typing import cast

from applications.operational_monitoring.weekly_result import (
    WeeklyOperationalSummaryResult,
)
from core.operations import (
    OperationalCheck,
    OperationalNotificationError,
    OperationalState,
    WeeklyOperationalSummaryChannel,
    WeeklyOperationalSummaryEngine,
    WeeklyOperationalSummaryStore,
)


class WeeklyOperationalSummaryWorkflow:
    """Persist weekly evidence and deliver an eligible preceding summary."""

    def __init__(
        self,
        store: WeeklyOperationalSummaryStore,
        engine: WeeklyOperationalSummaryEngine,
        channel: WeeklyOperationalSummaryChannel,
    ) -> None:
        """Validate and retain injected collaborators."""
        _require_method(store, "load", "store")
        _require_method(store, "save", "store")
        if not isinstance(engine, WeeklyOperationalSummaryEngine):
            raise TypeError("engine must be a WeeklyOperationalSummaryEngine")
        _require_method(channel, "send", "channel")
        self._store = cast(WeeklyOperationalSummaryStore, store)
        self._engine = engine
        self._channel = cast(WeeklyOperationalSummaryChannel, channel)

    def run(
        self,
        check: OperationalCheck,
        previous_state: OperationalState,
        current_state: OperationalState,
        local_date: date,
        local_time: time,
        delivery_time: time = time(8, 0),
    ) -> WeeklyOperationalSummaryResult:
        """Record one check and optionally deliver the prior complete week."""
        if not isinstance(check, OperationalCheck):
            raise TypeError("check must be an OperationalCheck")
        if not isinstance(previous_state, OperationalState):
            raise TypeError("previous_state must be an OperationalState")
        if not isinstance(current_state, OperationalState):
            raise TypeError("current_state must be an OperationalState")
        _validate_date(local_date)
        _validate_time(local_time, "local_time")
        _validate_time(delivery_time, "delivery_time")
        period_start = local_date - timedelta(days=local_date.weekday())
        current = self._store.load(period_start) or self._engine.initial(period_start)
        current = self._engine.record(
            current,
            local_date,
            check,
            previous_state,
            current_state,
        )
        self._store.save(current)
        if local_date == period_start and local_time < delivery_time:
            return WeeklyOperationalSummaryResult(current)
        previous = self._store.load(period_start - timedelta(days=7))
        if (
            previous is None
            or previous.total_failed_cycles == 0
            or previous.delivered_at is not None
        ):
            return WeeklyOperationalSummaryResult(current)
        report = self._engine.report(previous, check.timestamp)
        reserved = self._engine.mark_delivered(previous, check.timestamp)
        self._store.save(reserved)
        try:
            self._channel.send(report)
        except OperationalNotificationError as error:
            self._store.save(self._engine.release_delivery(reserved))
            return WeeklyOperationalSummaryResult(
                current,
                notification_error=error,
            )
        return WeeklyOperationalSummaryResult(current, report_sent=report)


def _require_method(value: object, method: str, name: str) -> None:
    if not callable(getattr(value, method, None)):
        raise TypeError(f"{name} must expose a callable {method} method")


def _validate_date(value: object) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError("local_date must be a date")


def _validate_time(value: object, name: str) -> None:
    if not isinstance(value, time):
        raise TypeError(f"{name} must be a time")
    if value.tzinfo is not None:
        raise ValueError(f"{name} must be naive local time")
