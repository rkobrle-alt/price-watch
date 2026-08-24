"""Tests for deterministic weekly operational summaries."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest

from core.operations import (
    OperationalCheck,
    OperationalFailureCount,
    OperationalFailureKind,
    OperationalHealthEngine,
    OperationalHealthStatus,
    OperationalState,
    WeeklyOperationalReport,
    WeeklyOperationalSummary,
    WeeklyOperationalSummaryEngine,
)

MONDAY = date(2026, 8, 17)
NOW = datetime(2026, 8, 17, 8, 0, tzinfo=UTC)


def _transition(
    previous: OperationalState,
    offset: int,
    kind: OperationalFailureKind | None,
) -> tuple[OperationalCheck, OperationalState]:
    check = OperationalCheck(NOW + timedelta(minutes=offset), kind)
    return check, OperationalHealthEngine().evaluate(previous, check)


def test_engine_aggregates_incidents_recovery_causes_and_report() -> None:
    engine = WeeklyOperationalSummaryEngine()
    summary = engine.initial(MONDAY)
    state = OperationalState.initial()
    check, failed = _transition(state, 1, OperationalFailureKind.PARTIAL_PROVIDER_FAILURE)
    summary = engine.record(summary, MONDAY, check, state, failed)
    check2, failed2 = _transition(failed, 2, OperationalFailureKind.CATALOG_UNAVAILABLE)
    summary = engine.record(summary, MONDAY, check2, failed, failed2)
    check3, recovered = _transition(failed2, 3, None)
    summary = engine.record(summary, MONDAY, check3, failed2, recovered)

    assert summary.failure_counts == (
        OperationalFailureCount(OperationalFailureKind.CATALOG_UNAVAILABLE, 1),
        OperationalFailureCount(
            OperationalFailureKind.PARTIAL_PROVIDER_FAILURE,
            1,
        ),
    )
    assert summary.total_failed_cycles == 2
    assert summary.incident_count == 1
    assert summary.recovery_count == 1
    assert summary.longest_failure_streak == 2
    assert summary.current_failure_streak == 0
    report = engine.report(summary, NOW + timedelta(days=7))
    assert report.period_end == date(2026, 8, 23)
    assert report.message == (
        "Týdenní souhrn provozních chyb Price Watch\n"
        "Období: 2026-08-17 až 2026-08-23\n"
        "Chybné cykly: 2\nIncidenty: 1\nZotavení: 1\n"
        "Nejdelší série chyb: 2\n"
        "První chyba: 2026-08-17T08:01:00+00:00\n"
        "Poslední chyba: 2026-08-17T08:02:00+00:00\n"
        "Příčiny:\n- catalog_unavailable: 1\n"
        "- partial_provider_failure: 1"
    )
    reserved = engine.mark_delivered(summary, report.created_at)
    assert reserved.delivered_at == report.created_at
    assert engine.release_delivery(reserved).delivered_at is None
    with pytest.raises(FrozenInstanceError):
        summary.total_failed_cycles = 4  # type: ignore[misc]


def test_healthy_only_week_retains_recovery_without_report() -> None:
    engine = WeeklyOperationalSummaryEngine()
    previous = OperationalState(
        OperationalHealthStatus.DEGRADED,
        OperationalFailureKind.PROVIDER_FAILURE,
        2,
        NOW - timedelta(days=1),
        NOW - timedelta(days=1),
        None,
        False,
        None,
        None,
    )
    check, current = _transition(previous, 0, None)
    summary = engine.record(engine.initial(MONDAY), MONDAY, check, previous, current)
    assert summary.total_failed_cycles == 0
    assert summary.recovery_count == 1
    with pytest.raises(ValueError, match="empty"):
        engine.report(summary, NOW)
    with pytest.raises(ValueError, match="empty"):
        engine.mark_delivered(summary, NOW)


def test_engine_suppresses_pending_failure_and_legacy_recovery() -> None:
    engine = OperationalHealthEngine()
    state = OperationalState.initial()
    for offset in range(3):
        check, state = _transition(
            state,
            offset,
            OperationalFailureKind.PROVIDER_FAILURE,
        )
    suppressed = engine.suppress_notification(state)
    assert suppressed.pending_notification is None
    assert suppressed.incident_notified is False
    assert engine.suppress_notification(suppressed) is suppressed
    notified = engine.acknowledge_notification(
        state,
        state.pending_notification,
    )
    _, recovered = _transition(notified, 4, None)
    cleared = engine.suppress_notification(recovered)
    assert cleared.incident_started_at is None
    assert cleared.incident_notified is False


@pytest.mark.parametrize(
    "summary",
    (
        WeeklyOperationalSummary(MONDAY),
        WeeklyOperationalSummary(MONDAY, recovery_count=1),
    ),
)
def test_summary_accepts_empty_failure_evidence(summary: WeeklyOperationalSummary) -> None:
    assert summary.first_failure_at is None


@pytest.mark.parametrize(
    ("factory", "error"),
    (
        (lambda: OperationalFailureCount("x", 1), TypeError),
        (lambda: OperationalFailureCount(OperationalFailureKind.PROVIDER_FAILURE, True), TypeError),
        (lambda: OperationalFailureCount(OperationalFailureKind.PROVIDER_FAILURE, 0), ValueError),
        (lambda: WeeklyOperationalSummary(datetime(2026, 8, 17)), TypeError),
        (lambda: WeeklyOperationalSummary(date(2026, 8, 18)), ValueError),
        (lambda: WeeklyOperationalSummary(MONDAY, []), TypeError),
        (lambda: WeeklyOperationalSummary(MONDAY, (object(),)), TypeError),
        (lambda: WeeklyOperationalSummary(MONDAY, total_failed_cycles=-1), ValueError),
        (lambda: WeeklyOperationalReport(MONDAY, MONDAY, "x", NOW), ValueError),
        (lambda: WeeklyOperationalReport(MONDAY, date(2026, 8, 23), 1, NOW), TypeError),
        (lambda: WeeklyOperationalReport(MONDAY, date(2026, 8, 23), " ", NOW), ValueError),
    ),
)
def test_weekly_values_reject_invalid_data(factory: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        cast(object, factory)()


def test_engine_rejects_invalid_arguments_and_delivery_state() -> None:
    engine = WeeklyOperationalSummaryEngine()
    summary = engine.initial(MONDAY)
    check, current = _transition(OperationalState.initial(), 0, None)
    with pytest.raises(TypeError, match="summary"):
        engine.record(cast(WeeklyOperationalSummary, object()), MONDAY, check, OperationalState.initial(), current)
    with pytest.raises(ValueError, match="period"):
        engine.record(summary, MONDAY + timedelta(days=7), check, OperationalState.initial(), current)
    with pytest.raises(TypeError, match="check"):
        engine.record(summary, MONDAY, cast(OperationalCheck, object()), OperationalState.initial(), current)
    with pytest.raises(TypeError, match="previous_state"):
        engine.record(summary, MONDAY, check, cast(OperationalState, object()), current)
    with pytest.raises(TypeError, match="current_state"):
        engine.record(summary, MONDAY, check, OperationalState.initial(), cast(OperationalState, object()))
    with pytest.raises(ValueError, match="represent"):
        engine.record(summary, MONDAY, check, OperationalState.initial(), OperationalState.initial())
    failed_check, failed = _transition(
        OperationalState.initial(),
        1,
        OperationalFailureKind.PROVIDER_FAILURE,
    )
    nonempty = engine.record(summary, MONDAY, failed_check, OperationalState.initial(), failed)
    reserved = engine.mark_delivered(nonempty, NOW)
    with pytest.raises(ValueError, match="already"):
        engine.mark_delivered(reserved, NOW)
    with pytest.raises(ValueError, match="aware"):
        engine.mark_delivered(nonempty, datetime(2026, 8, 17))


def test_summary_rejects_aggregate_invariants() -> None:
    count = OperationalFailureCount(OperationalFailureKind.PROVIDER_FAILURE, 1)
    for changes in (
        {"failure_counts": (count, count), "total_failed_cycles": 2},
        {"failure_counts": (count,), "total_failed_cycles": 2},
        {"current_failure_streak": 1},
        {"longest_failure_streak": 1},
        {"total_failed_cycles": 1},
        {"delivered_at": NOW},
        {
            "failure_counts": (count,),
            "total_failed_cycles": 1,
            "first_failure_at": NOW,
            "last_failure_at": NOW - timedelta(minutes=1),
        },
        {
            "failure_counts": (count,),
            "total_failed_cycles": 1,
            "first_failure_at": NOW,
        },
    ):
        with pytest.raises(ValueError):
            replace(WeeklyOperationalSummary(MONDAY), **changes)


def test_weekly_timestamp_and_count_helpers_reject_wrong_types() -> None:
    with pytest.raises(TypeError, match="created_at"):
        WeeklyOperationalReport(
            MONDAY,
            date(2026, 8, 23),
            "x",
            cast(datetime, object()),
        )
    with pytest.raises(TypeError, match="total_failed_cycles"):
        WeeklyOperationalSummary(MONDAY, total_failed_cycles=True)
