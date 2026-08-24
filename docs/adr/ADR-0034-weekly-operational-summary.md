# ADR-0034: Weekly Operational Error Summary

## Status

Accepted

## Context

ADR-0031 sends one email when a sustained incident reaches `failed` and one
when an acknowledged incident recovers. Repeated partial Lidl failures can
alternate between failed and healthy states, creating more service email than
is useful even though the durable Home Assistant health sensors remain
valuable.

The operator has approved a quieter policy: no immediate operational failure
or recovery email, and at most one summary of the preceding week's errors on
Monday after 08:00 Europe/Prague. Daily discount email is unchanged.

## Decision

Immediate operational transition delivery becomes an optional Home Assistant
catalog policy. Its existing default remains enabled when the new option is
absent, preserving the 1.0 contract. The packaged default disables it.
Suppression clears a pending transition without claiming external delivery;
health transitions, persistence, logs and Home Assistant diagnostics continue.

Weekly reporting is a separate optional workflow. Its existing-installation
default is disabled and its packaged default is enabled. Every completed
catalog cycle is assigned by the Application to a Europe/Prague calendar date
and recorded in a durable Monday-to-Sunday bucket. Core does not read a clock
or timezone.

The bucket retains:

- failed-cycle counts by `OperationalFailureKind`;
- total failed cycles;
- incident and recovery counts;
- the longest consecutive failure sequence;
- first and last failure timestamps;
- an optional delivery timestamp.

An incident begins when a failed check follows an `ok` state. A recovery is a
healthy check following an unhealthy state. Only failed checks affect failure
counts and timestamps.

From Monday 08:00 local time until the end of the current week, the workflow
considers the immediately preceding complete Monday-to-Sunday bucket. This
allows a delayed start or reported delivery failure to retry after Monday. A
bucket with no failed cycles produces no email. A non-empty bucket is marked
delivered before one channel call. A reported delivery failure removes the
mark for retry in a later cycle. A retained delivery timestamp prevents
duplicates across cycles and restarts.
The accepted reservation-before-delivery hard-stop trade-off matches the daily
digest: a process stop after marking and before external acceptance may
suppress one summary rather than duplicate email.

The deterministic Czech summary contains the period, total failed cycles,
incident and recovery counts, longest failure sequence, first and last failure
times and non-zero cause counts in enum order. Its title is
`{notification_title} Weekly Health Summary`.

The message is exactly:

```text
Týdenní souhrn provozních chyb Price Watch
Období: <YYYY-MM-DD> až <YYYY-MM-DD>
Chybné cykly: <count>
Incidenty: <count>
Zotavení: <count>
Nejdelší série chyb: <count>
První chyba: <ISO timestamp>
Poslední chyba: <ISO timestamp>
Příčiny:
- <failure value>: <count>
```

Only non-zero causes appear. A report is never generated for an empty bucket,
so both timestamps and at least one cause are always present.

## Persistence

SQLite schema 7 adds `weekly_operational_summaries` keyed by ISO period-start
date with one strict versioned JSON payload. Schema 6 migrates transactionally
without changing existing rows. Valid schemas 1 through 6 continue through
the established sequential migrations.

## Public API

`core.operations` adds immutable `OperationalFailureCount`,
`WeeklyOperationalSummary` and `WeeklyOperationalReport`, deterministic
`WeeklyOperationalSummaryEngine`, `WeeklyOperationalSummaryStore` and
`WeeklyOperationalSummaryChannel`.
`OperationalHealthEngine` adds `suppress_notification(state)`.

`applications.operational_monitoring` adds
`WeeklyOperationalSummaryResult` and `WeeklyOperationalSummaryWorkflow`.
The existing `OperationalMonitoringWorkflow` constructor gains the optional
final keyword `notifications_enabled: bool = True`.
`OperationalMonitoringResult` gains the backward-compatible final field
`previous_state: OperationalState | None = None`.

`infrastructure.persistence.sqlite` adds
`SqliteWeeklyOperationalSummaryStore`. `infrastructure.homeassistant` adds
`HomeAssistantWeeklyOperationalSummaryChannel`.

Home Assistant options add:

```text
immediate_operational_notifications_enabled: bool
weekly_operational_summary_enabled: bool
weekly_operational_summary_time: HH:MM
```

The time option is valid only when weekly reporting is enabled. Weekly
reporting and immediate operational notification policy require catalog mode.
Existing option documents retain the ADR-0031 behavior when the new keys are
absent.

## Dependency Direction

Core remains deterministic and standard-library-only. The reusable workflow
depends on Core contracts. SQLite and Home Assistant adapters remain in
Infrastructure. `applications.homeassistant` supplies local date/time and
composes concrete adapters.

## Consequences

The deployment stops noisy service email while retaining immediate dashboard
diagnostics and durable evidence. The daily discount report is unaffected.
One small SQLite row is retained per observed week. The first summary after
upgrade can include only checks recorded after upgrade; no historical error
events are inferred from the current health snapshot.
