# STORY-030: Operational Resilience and Recovery

## Objective

Implement ADR-0031 for Home Assistant catalog mode without changing existing
product monitoring, rule evaluation, catalog status or daily-digest behavior.

## Scope

- add deterministic provider-neutral operational health contracts;
- persist health and last successful digest metadata in SQLite schema 5;
- classify Lidl transport and data errors without breaking `ProviderError`;
- publish durable health and digest diagnostics to Home Assistant;
- deliver one sustained-failure and one acknowledged-incident recovery
  notification through the configured notify entity;
- keep delivery failures non-fatal and retry pending messages.

Explicit mode, CLI behavior, product notifications, digest content, retention
semantics and existing Home Assistant entities are out of scope.

## Core Package

Create `core/operations/` with an explicit public `__init__.py`. Public values
are frozen slotted dataclasses or enums. Timestamps are timezone-aware and
caller supplied.

`OperationalCheck` contains `timestamp` and an optional failure kind.
`DailyDigestDelivery` contains calendar date, delivery timestamp, non-negative
product count and promotion flag. `OperationalState` contains the fields from
ADR-0031 and provides `initial()`.

The exact `OperationalState` fields are:

```python
status: OperationalHealthStatus
failure_kind: OperationalFailureKind | None
consecutive_failure_cycles: int
incident_started_at: datetime | None
last_checked_at: datetime | None
last_recovered_at: datetime | None
incident_notified: bool
pending_notification: OperationalNotificationKind | None
last_digest_delivery: DailyDigestDelivery | None
```

Enum strings are `ok`, `degraded`, `failed`; `catalog_unavailable`,
`provider_data_incompatible`, `provider_unavailable`, `provider_failure`,
`partial_provider_failure`, `promotion_unavailable`; and `failure`, `recovery`.

`OperationalNotification` contains `kind`, `message` and `created_at`.
Failure text is exactly:

```text
Price Watch operational failure
Cause: <failure value>
Consecutive failed cycles: <count>
Incident started: <ISO timestamp>
Last checked: <ISO timestamp>
```

Recovery text is exactly:

```text
Price Watch operational recovery
Incident started: <ISO timestamp>
Recovered at: <ISO timestamp>
```

`OperationalHealthEngine` exposes:

```python
evaluate(previous, check, failure_threshold=3) -> OperationalState
record_digest_delivery(state, delivery) -> OperationalState
pending_notification(state) -> OperationalNotification | None
acknowledge_notification(state, kind) -> OperationalState
```

Evaluation and deterministic notification content follow ADR-0031 exactly.
Acknowledging a different kind from the pending kind raises `ValueError`.
The threshold is a positive integer and rejects `bool`. A digest delivery
older than the retained delivery timestamp raises `ValueError`.

Protocols expose `OperationalStateStore.load/save` and
`OperationalNotificationChannel.send`. Export subsystem persistence and
notification errors.

## Provider SDK

Add and export documented `ProviderTransportError(ProviderError)` and
`ProviderDataError(ProviderError)`. `LidlParksideProvider` maps HTTP failures
to transport and product-data failures to data errors while preserving
URL-prefixed diagnostics and partial ordering.

## SQLite

Migrate schema 4 to 5 transactionally and validate the singleton table.
Create and export `SqliteOperationalStateStore(path, timeout_seconds=5)`.
Construction performs no I/O. `load()` returns the initial state without a
row. `save()` atomically replaces singleton ID 1. Encoding is versioned,
lossless and strict. Malformed data raises `OperationalStateError`.

Existing retention, migration archive, catalog, observation and reservation
behavior remains unchanged. Migration tests cover clean creation, supported
predecessors and invalid schema 5.

## Application Workflow

Create `applications/operational_monitoring/` with an immutable result and
workflow. The workflow accepts a store, engine and channel. `run(check,
digest_delivery=None)` loads state, records a supplied delivery, evaluates,
saves, sends any pending notification and acknowledges it with a second save.
`OperationalNotificationError` is returned with the saved pending state;
persistence and unexpected failures propagate.

`OperationalMonitoringResult` contains `state`, `notification_sent` and
`notification_error`. The sent value is the acknowledged notification kind or
`None`; the error is `OperationalNotificationError | None` and is mutually
exclusive with a sent kind.

Catalog-cycle classification uses ADR-0031 priority. A `SENT` digest creates
delivery metadata; other statuses preserve the last successful delivery.
Total provider failure requires selected references, zero successful products
and one provider error per selected reference. All-data and all-transport
tuples select their specific kinds; every other total tuple is generic. Any
smaller non-zero provider-error count is partial. No selected references is
healthy unless catalog or promotion evidence says otherwise.

## Home Assistant Infrastructure and Composition

Add and export `HomeAssistantOperationalStatusPublisher` and
`HomeAssistantOperationalNotificationChannel`. The publisher validates before
side effects and publishes digest before health with exact ADR-0031 payloads.
The channel sends the message unchanged and translates `HomeAssistantError`
with cause chaining.

The publisher method is `publish(state, current_digest_status) -> None`. The
status is the daily-digest enum string, or `disabled` when not composed. States
and attributes are exactly those listed in ADR-0031.

Catalog composition reuses the SQLite path, REST client, notify entity and
title. Operational processing runs after the digest. Publication and delivery
errors are logged, mark `status_published=false` and do not stop later cycles.
Persistence and unexpected errors retain current fatal behavior.

Cycle output adds:

```text
health_status=<value> health_failures=<count> operational_notification=<none|failure|recovery|retry>
```

`failure` and `recovery` mean successful delivery in that cycle. `retry` means
delivery failed and remains pending. `none` means no operational notification
was attempted. The workflow runs before its state publisher; publication
failure cannot change saved health.

## Tests

Cover every model invariant, state transition, changed kind, threshold,
notification acknowledgement, digest update, provider subtype mapping, schema
creation/migration/validation, exact round-trip, workflow ordering and retry,
Home Assistant payload, classification priority, composition, dependency
boundary and a restart-spanning integration incident/recovery scenario.

No test is skipped. Statement and branch coverage remains 100%.

## Acceptance Criteria

- existing monitoring and state contracts remain unchanged;
- one or two failed cycles are `degraded` without email;
- the third is `failed` and creates one failure email;
- further failed cycles create no duplicate incident email;
- undelivered operational email remains pending and retries;
- one healthy cycle returns to `ok` and sends recovery only for an
  acknowledged incident;
- health and last digest delivery survive restart;
- failure categories are distinguishable;
- schema migration preserves every existing row;
- no new option, permission, credential or port is introduced;
- public APIs are documented and exported;
- all tests pass with 100% statement and branch coverage;
- no TODO, placeholder, pass statement, commented code or dead code remains.

## Readiness Review

Specification is implementation-ready.
