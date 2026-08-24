"""Restart-spanning acceptance test for weekly operational delivery."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path

from applications.operational_monitoring import WeeklyOperationalSummaryWorkflow
from core.operations import (
    OperationalCheck,
    OperationalFailureKind,
    OperationalHealthEngine,
    OperationalState,
    WeeklyOperationalReport,
    WeeklyOperationalSummaryEngine,
)
from infrastructure.persistence.sqlite import SqliteWeeklyOperationalSummaryStore


@dataclass(slots=True)
class _Channel:
    reports: list[WeeklyOperationalReport] = field(default_factory=list)

    def send(self, report: WeeklyOperationalReport) -> None:
        self.reports.append(report)


def _workflow(path: Path, channel: _Channel) -> WeeklyOperationalSummaryWorkflow:
    return WeeklyOperationalSummaryWorkflow(
        SqliteWeeklyOperationalSummaryStore(path),
        WeeklyOperationalSummaryEngine(),
        channel,
    )


def test_weekly_report_is_durable_and_not_repeated_after_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    channel = _Channel()
    health = OperationalHealthEngine()
    initial = OperationalState.initial()
    failed_check = OperationalCheck(
        datetime(2026, 8, 23, 20, 0, tzinfo=UTC),
        OperationalFailureKind.PARTIAL_PROVIDER_FAILURE,
    )
    failed = health.evaluate(initial, failed_check)
    _workflow(path, channel).run(
        failed_check,
        initial,
        failed,
        date(2026, 8, 23),
        time(22),
    )

    recovered_check = OperationalCheck(
        datetime(2026, 8, 24, 6, 0, tzinfo=UTC),
        None,
    )
    recovered = health.evaluate(failed, recovered_check)
    delivered = _workflow(path, channel).run(
        recovered_check,
        failed,
        recovered,
        date(2026, 8, 24),
        time(8),
    )

    assert delivered.report_sent is channel.reports[0]
    healthy_check = OperationalCheck(
        datetime(2026, 8, 25, 6, 0, tzinfo=UTC),
        None,
    )
    healthy = health.evaluate(recovered, healthy_check)
    duplicate = _workflow(path, channel).run(
        healthy_check,
        recovered,
        healthy,
        date(2026, 8, 25),
        time(8),
    )
    assert duplicate.report_sent is None
    assert len(channel.reports) == 1
