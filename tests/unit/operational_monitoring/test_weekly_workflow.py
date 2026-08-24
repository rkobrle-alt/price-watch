"""Tests for weekly operational summary orchestration."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import cast

import pytest

from applications.operational_monitoring import (
    WeeklyOperationalSummaryResult,
    WeeklyOperationalSummaryWorkflow,
)
from core.operations import (
    OperationalCheck,
    OperationalFailureKind,
    OperationalHealthEngine,
    OperationalNotificationError,
    OperationalState,
    WeeklyOperationalReport,
    WeeklyOperationalSummary,
    WeeklyOperationalSummaryEngine,
)

MONDAY = date(2026, 8, 17)
NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)


@dataclass
class _Store:
    values: dict[date, WeeklyOperationalSummary] = field(default_factory=dict)

    def load(self, period_start: date) -> WeeklyOperationalSummary | None:
        return self.values.get(period_start)

    def save(self, summary: WeeklyOperationalSummary) -> None:
        self.values[summary.period_start] = summary


@dataclass
class _Channel:
    error: OperationalNotificationError | None = None
    reports: list[WeeklyOperationalReport] = field(default_factory=list)

    def send(self, report: WeeklyOperationalReport) -> None:
        self.reports.append(report)
        if self.error is not None:
            raise self.error


def _failed_transition(timestamp: datetime) -> tuple[OperationalCheck, OperationalState, OperationalState]:
    previous = OperationalState.initial()
    check = OperationalCheck(timestamp, OperationalFailureKind.PARTIAL_PROVIDER_FAILURE)
    current = OperationalHealthEngine().evaluate(previous, check)
    return check, previous, current


def test_workflow_records_before_time_then_delivers_once_after_time() -> None:
    store = _Store()
    channel = _Channel()
    workflow = WeeklyOperationalSummaryWorkflow(
        store,
        WeeklyOperationalSummaryEngine(),
        channel,
    )
    prior_check, prior_state, prior_current = _failed_transition(NOW - timedelta(days=1))
    prior = WeeklyOperationalSummaryEngine().record(
        WeeklyOperationalSummaryEngine().initial(MONDAY),
        date(2026, 8, 23),
        prior_check,
        prior_state,
        prior_current,
    )
    store.save(prior)
    check, previous, current = _failed_transition(NOW)

    before = workflow.run(check, previous, current, date(2026, 8, 24), time(7, 59))
    sent = workflow.run(check, previous, current, date(2026, 8, 24), time(8, 0))
    duplicate = workflow.run(check, previous, current, date(2026, 8, 24), time(9, 0))

    assert before.report_sent is None
    assert sent.report_sent == channel.reports[0]
    assert duplicate.report_sent is None
    assert store.values[MONDAY].delivered_at == NOW


def test_workflow_retries_reported_delivery_error_later_in_week() -> None:
    engine = WeeklyOperationalSummaryEngine()
    store = _Store()
    channel = _Channel(OperationalNotificationError("offline"))
    workflow = WeeklyOperationalSummaryWorkflow(store, engine, channel)
    check, previous, current = _failed_transition(NOW - timedelta(days=1))
    store.save(engine.record(engine.initial(MONDAY), date(2026, 8, 23), check, previous, current))
    current_check, before, after = _failed_transition(NOW + timedelta(days=1))

    failed = workflow.run(current_check, before, after, date(2026, 8, 25), time(9))
    assert failed.notification_error is channel.error
    assert store.values[MONDAY].delivered_at is None
    channel.error = None
    retried = workflow.run(current_check, before, after, date(2026, 8, 25), time(10))
    assert retried.report_sent is not None


def test_workflow_skips_missing_and_empty_previous_week() -> None:
    workflow = WeeklyOperationalSummaryWorkflow(
        _Store(),
        WeeklyOperationalSummaryEngine(),
        _Channel(),
    )
    check, previous, current = _failed_transition(NOW)
    result = workflow.run(check, previous, current, date(2026, 8, 24), time(9))
    assert result.report_sent is None


def test_result_and_workflow_validate_public_arguments() -> None:
    summary = WeeklyOperationalSummary(MONDAY)
    report = WeeklyOperationalReport(MONDAY, date(2026, 8, 23), "x", NOW)
    error = OperationalNotificationError("x")
    with pytest.raises(TypeError, match="current_summary"):
        WeeklyOperationalSummaryResult(cast(WeeklyOperationalSummary, object()))
    with pytest.raises(TypeError, match="report_sent"):
        WeeklyOperationalSummaryResult(summary, cast(WeeklyOperationalReport, object()))
    with pytest.raises(ValueError, match="mutually"):
        WeeklyOperationalSummaryResult(summary, report, error)
    with pytest.raises(TypeError, match="notification_error"):
        WeeklyOperationalSummaryResult(
            summary,
            notification_error=cast(OperationalNotificationError, object()),
        )
    for arguments, name in (
        ((object(), WeeklyOperationalSummaryEngine(), _Channel()), "store"),
        ((_Store(), object(), _Channel()), "engine"),
        ((_Store(), WeeklyOperationalSummaryEngine(), object()), "channel"),
    ):
        with pytest.raises(TypeError, match=name):
            WeeklyOperationalSummaryWorkflow(*cast(tuple, arguments))

    workflow = WeeklyOperationalSummaryWorkflow(
        _Store(),
        WeeklyOperationalSummaryEngine(),
        _Channel(),
    )
    check, previous, current = _failed_transition(NOW)
    invalid_runs = (
        ((object(), previous, current, MONDAY, time(8)), TypeError),
        ((check, object(), current, MONDAY, time(8)), TypeError),
        ((check, previous, object(), MONDAY, time(8)), TypeError),
        ((check, previous, current, datetime(2026, 8, 24), time(8)), TypeError),
        ((check, previous, current, MONDAY, object()), TypeError),
        ((check, previous, current, MONDAY, time(8, tzinfo=UTC)), ValueError),
        ((check, previous, current, MONDAY, time(8), object()), TypeError),
        ((check, previous, current, MONDAY, time(8), time(8, tzinfo=UTC)), ValueError),
    )
    for arguments, exception_type in invalid_runs:
        with pytest.raises(exception_type):
            workflow.run(*cast(tuple, arguments))
