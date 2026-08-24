"""Deterministic weekly operational error aggregation."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import cast

from core.operations.enums import OperationalFailureKind, OperationalHealthStatus
from core.operations.model import OperationalCheck, OperationalState


@dataclass(frozen=True, slots=True)
class OperationalFailureCount:
    """Count failed cycles for one operational cause."""

    kind: OperationalFailureKind
    count: int

    def __post_init__(self) -> None:
        """Validate cause and positive exact count."""
        if not isinstance(self.kind, OperationalFailureKind):
            raise TypeError("kind must be an OperationalFailureKind")
        _validate_count(self.count, "count")
        if self.count == 0:
            raise ValueError("count must be greater than zero")


@dataclass(frozen=True, slots=True)
class WeeklyOperationalSummary:
    """Retain one Monday-to-Sunday operational error bucket."""

    period_start: date
    failure_counts: tuple[OperationalFailureCount, ...] = ()
    total_failed_cycles: int = 0
    incident_count: int = 0
    recovery_count: int = 0
    longest_failure_streak: int = 0
    current_failure_streak: int = 0
    first_failure_at: datetime | None = None
    last_failure_at: datetime | None = None
    delivered_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate weekly chronology and aggregate invariants."""
        _validate_date(self.period_start, "period_start")
        if self.period_start.weekday() != 0:
            raise ValueError("period_start must be a Monday")
        if not isinstance(self.failure_counts, tuple):
            raise TypeError("failure_counts must be a tuple")
        if not all(isinstance(item, OperationalFailureCount) for item in self.failure_counts):
            raise TypeError("failure_counts must contain OperationalFailureCount values")
        kinds = tuple(item.kind for item in self.failure_counts)
        expected = tuple(kind for kind in OperationalFailureKind if kind in kinds)
        if kinds != expected:
            raise ValueError("failure_counts must be unique and in enum order")
        for value, name in (
            (self.total_failed_cycles, "total_failed_cycles"),
            (self.incident_count, "incident_count"),
            (self.recovery_count, "recovery_count"),
            (self.longest_failure_streak, "longest_failure_streak"),
            (self.current_failure_streak, "current_failure_streak"),
        ):
            _validate_count(value, name)
        if sum(item.count for item in self.failure_counts) != self.total_failed_cycles:
            raise ValueError("failure counts must sum to total_failed_cycles")
        if self.current_failure_streak > self.longest_failure_streak:
            raise ValueError("current failure streak cannot exceed longest streak")
        if self.longest_failure_streak > self.total_failed_cycles:
            raise ValueError("longest failure streak cannot exceed failed cycles")
        for value, name in (
            (self.first_failure_at, "first_failure_at"),
            (self.last_failure_at, "last_failure_at"),
            (self.delivered_at, "delivered_at"),
        ):
            if value is not None:
                _validate_timestamp(value, name)
        has_times = self.first_failure_at is not None and self.last_failure_at is not None
        if has_times != (self.total_failed_cycles > 0):
            raise ValueError("failure timestamps must match failed-cycle presence")
        if has_times and self.first_failure_at > self.last_failure_at:
            raise ValueError("first_failure_at cannot follow last_failure_at")
        if self.delivered_at is not None and self.total_failed_cycles == 0:
            raise ValueError("an empty summary cannot be delivered")


@dataclass(frozen=True, slots=True)
class WeeklyOperationalReport:
    """Describe one channel-neutral weekly operational report."""

    period_start: date
    period_end: date
    message: str
    created_at: datetime

    def __post_init__(self) -> None:
        """Validate report period, content and timestamp."""
        _validate_date(self.period_start, "period_start")
        _validate_date(self.period_end, "period_end")
        if self.period_start.weekday() != 0 or self.period_end != self.period_start + timedelta(days=6):
            raise ValueError("report period must be Monday through Sunday")
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")
        if not self.message.strip():
            raise ValueError("message cannot be blank")
        _validate_timestamp(self.created_at, "created_at")


class WeeklyOperationalSummaryEngine:
    """Aggregate and format weekly operational evidence without side effects."""

    def initial(self, period_start: date) -> WeeklyOperationalSummary:
        """Create an empty validated weekly bucket."""
        return WeeklyOperationalSummary(period_start)

    def record(
        self,
        summary: WeeklyOperationalSummary,
        local_date: date,
        check: OperationalCheck,
        previous_state: OperationalState,
        current_state: OperationalState,
    ) -> WeeklyOperationalSummary:
        """Record one explicit completed operational transition."""
        _validate_summary(summary)
        _validate_date(local_date, "local_date")
        if summary.period_start != local_date - timedelta(days=local_date.weekday()):
            raise ValueError("local_date must belong to summary period")
        if not isinstance(check, OperationalCheck):
            raise TypeError("check must be an OperationalCheck")
        _validate_state(previous_state, "previous_state")
        _validate_state(current_state, "current_state")
        if current_state.last_checked_at != check.timestamp:
            raise ValueError("current_state must represent check")

        failed = check.failure_kind is not None
        counts = _updated_counts(summary.failure_counts, check.failure_kind)
        current_streak = summary.current_failure_streak + 1 if failed else 0
        first_failure = summary.first_failure_at
        if failed and first_failure is None:
            first_failure = check.timestamp
        return replace(
            summary,
            failure_counts=counts,
            total_failed_cycles=summary.total_failed_cycles + int(failed),
            incident_count=summary.incident_count
            + int(failed and previous_state.status is OperationalHealthStatus.OK),
            recovery_count=summary.recovery_count
            + int(not failed and previous_state.status is not OperationalHealthStatus.OK),
            longest_failure_streak=max(summary.longest_failure_streak, current_streak),
            current_failure_streak=current_streak,
            first_failure_at=first_failure,
            last_failure_at=check.timestamp if failed else summary.last_failure_at,
        )

    def report(
        self,
        summary: WeeklyOperationalSummary,
        created_at: datetime,
    ) -> WeeklyOperationalReport:
        """Format one deterministic non-empty Czech report."""
        _validate_summary(summary)
        _validate_timestamp(created_at, "created_at")
        if summary.total_failed_cycles == 0:
            raise ValueError("cannot report an empty summary")
        first = cast(datetime, summary.first_failure_at)
        last = cast(datetime, summary.last_failure_at)
        causes = "\n".join(
            f"- {item.kind.value}: {item.count}" for item in summary.failure_counts
        )
        period_end = summary.period_start + timedelta(days=6)
        message = (
            "Týdenní souhrn provozních chyb Price Watch\n"
            f"Období: {summary.period_start.isoformat()} až {period_end.isoformat()}\n"
            f"Chybné cykly: {summary.total_failed_cycles}\n"
            f"Incidenty: {summary.incident_count}\n"
            f"Zotavení: {summary.recovery_count}\n"
            f"Nejdelší série chyb: {summary.longest_failure_streak}\n"
            f"První chyba: {first.isoformat()}\n"
            f"Poslední chyba: {last.isoformat()}\n"
            f"Příčiny:\n{causes}"
        )
        return WeeklyOperationalReport(summary.period_start, period_end, message, created_at)

    def mark_delivered(
        self,
        summary: WeeklyOperationalSummary,
        delivered_at: datetime,
    ) -> WeeklyOperationalSummary:
        """Retain the pre-delivery reservation timestamp."""
        _validate_summary(summary)
        _validate_timestamp(delivered_at, "delivered_at")
        if summary.total_failed_cycles == 0:
            raise ValueError("cannot deliver an empty summary")
        if summary.delivered_at is not None:
            raise ValueError("summary is already delivered")
        return replace(summary, delivered_at=delivered_at)

    def release_delivery(
        self,
        summary: WeeklyOperationalSummary,
    ) -> WeeklyOperationalSummary:
        """Release a reported failed delivery for later retry."""
        _validate_summary(summary)
        return replace(summary, delivered_at=None)


def _updated_counts(
    counts: tuple[OperationalFailureCount, ...],
    kind: OperationalFailureKind | None,
) -> tuple[OperationalFailureCount, ...]:
    if kind is None:
        return counts
    values = {item.kind: item.count for item in counts}
    values[kind] = values.get(kind, 0) + 1
    return tuple(
        OperationalFailureCount(candidate, values[candidate])
        for candidate in OperationalFailureKind
        if candidate in values
    )


def _validate_summary(value: object) -> None:
    if not isinstance(value, WeeklyOperationalSummary):
        raise TypeError("summary must be a WeeklyOperationalSummary")


def _validate_state(value: object, name: str) -> None:
    if not isinstance(value, OperationalState):
        raise TypeError(f"{name} must be an OperationalState")


def _validate_date(value: object, name: str) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{name} must be a date")


def _validate_timestamp(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _validate_count(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
