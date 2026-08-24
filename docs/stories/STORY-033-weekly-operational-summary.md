# STORY-033: Weekly Operational Error Summary

## Objective

Implement ADR-0034 as Price Watch 1.1.0 so the approved Home Assistant
deployment receives no immediate service incident/recovery email and at most
one error summary each Monday after 08:00 Europe/Prague.

## Scope

- preserve real-time operational health and all existing sensors;
- add backward-compatible immediate-delivery and weekly-summary options;
- aggregate completed catalog checks into durable weekly buckets;
- deliver only a non-empty preceding-week summary;
- preserve the daily discount digest and all product behavior;
- migrate SQLite schema 6 to 7 transactionally.

## Core

Create cohesive weekly summary model, store/channel Protocol and deterministic
engine modules under `core.operations`. Public values are frozen slotted
dataclasses. Counts reject `bool`, cannot be negative and cause tuples contain
each kind at most once in enum order. Dates are exact `date` values and all
timestamps are timezone-aware.

The exact values are:

```python
OperationalFailureCount(kind: OperationalFailureKind, count: int)

WeeklyOperationalSummary(
    period_start: date,
    failure_counts: tuple[OperationalFailureCount, ...] = (),
    total_failed_cycles: int = 0,
    incident_count: int = 0,
    recovery_count: int = 0,
    longest_failure_streak: int = 0,
    current_failure_streak: int = 0,
    first_failure_at: datetime | None = None,
    last_failure_at: datetime | None = None,
    delivered_at: datetime | None = None,
)

WeeklyOperationalReport(
    period_start: date,
    period_end: date,
    message: str,
    created_at: datetime,
)
```

`period_start` must be Monday. Failure-count sum equals total failed cycles;
first/last timestamps are both absent exactly for an empty summary. Delivery
does not alter accumulated counts.

The engine records one explicit check and the health state immediately before
and after it. It validates chronology and period membership, computes incident
and recovery transitions and formats the exact Czech weekly message specified
by ADR-0034. It performs no I/O and reads no clock.

Its public methods are:

```python
initial(period_start: date) -> WeeklyOperationalSummary
record(summary, local_date, check, previous_state, current_state) -> WeeklyOperationalSummary
report(summary, created_at) -> WeeklyOperationalReport
mark_delivered(summary, delivered_at) -> WeeklyOperationalSummary
release_delivery(summary) -> WeeklyOperationalSummary
```

The store exposes `load(period_start)` and `save(summary)`. The channel exposes
`send(report)`.

Add `OperationalHealthEngine.suppress_notification`. Suppressing failure
clears its pending value and keeps `incident_notified=False`. Suppressing a
legacy pending recovery clears the retained incident notification state. A
state without a pending notification is returned unchanged.

## Application

`OperationalMonitoringWorkflow(..., *, notifications_enabled=True)` retains
all existing behavior by default. When disabled, it saves the transitioned
state, suppresses a pending transition, saves the suppressed state and never
calls the channel.

`OperationalMonitoringResult` gains the final optional `previous_state` field.
The workflow always supplies the state loaded before the transition. Existing
manual construction remains compatible because the field defaults to `None`.

`WeeklyOperationalSummaryWorkflow` accepts store, engine and channel. Its
`run(check, previous_state, current_state, local_date, local_time)` records the
current bucket before checking eligibility for the preceding bucket. The
optional final `delivery_time` defaults to 08:00. Eligibility begins at that
time on Monday and remains open through Sunday, permitting delayed startup and
retry. It returns `WeeklyOperationalSummaryResult(current_summary,
report_sent=None, notification_error=None)`. The latter two values are
mutually exclusive. Persistence and unexpected errors propagate. Reported
channel failure clears the pre-delivery mark and is returned non-fatally.

## Infrastructure

Add strict versioned SQLite storage and schema 7 migration. Construction does
no I/O. Missing bucket returns `None`; save atomically replaces exactly one
period. Invalid persisted data raises `OperationalStateError`.

Add a Home Assistant weekly channel which uses the configured notify entity,
the exact ADR title and unchanged Core message. It translates
`HomeAssistantError` to `OperationalNotificationError` with cause chaining.

## Home Assistant

Add the three ADR options. Absence preserves 1.0 behavior: immediate enabled,
weekly disabled, time 08:00. Packaged defaults are immediate false, weekly
true and 08:00. Weekly options are catalog-only.

Catalog composition injects both workflows. Every completed operational check
records weekly evidence. The current operational state is still published
after processing. Weekly delivery failure is logged and marks publication
outcome false without stopping future cycles.

## Public API and Files

Export every new Core, Application and Infrastructure public object through
its package `__init__.py`. Update version authority, project metadata and App
manifest to 1.1.0. No existing public name, positional call form, option,
entity, schema reader or exception boundary is removed.

## Tests

Cover model invariants, every aggregation transition, ISO-week boundaries,
Monday/time eligibility, empty weeks, duplicate prevention, delivery retry,
restart behavior, suppression including legacy recovery, SQLite schema 7 and
round-trip failures, configuration compatibility, composition, exact channel
payload and a restart-spanning integration scenario.

All tests are offline, none is skipped, and statement and branch coverage
remain 100 percent.

## Acceptance Criteria

- approved deployment defaults to no immediate service email;
- weekly report is eligible Monday at/after 08:00 Europe/Prague;
- only preceding-week errors are included and empty weeks send nothing;
- one retained delivery prevents duplicate weekly email after restart;
- health sensors and daily discount email are unchanged;
- valid SQLite schema 6 migrates to 7 without data loss;
- existing option documents retain 1.0 behavior when new options are absent;
- all public APIs are documented and exported;
- all tests pass with 100 percent statement and branch coverage;
- no TODO, placeholder, pass statement, skipped test or dead code is added.

## Readiness Review

Specification is implementation-ready.
