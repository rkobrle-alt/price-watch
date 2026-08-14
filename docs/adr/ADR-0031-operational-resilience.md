# ADR-0031: Durable Operational Health and Recovery

## Status

Accepted

## Context

Price Watch exposes current-cycle errors, but a single failed product request
and a sustained provider outage appear through the same aggregate count. The
state is not durable, no incident transition is defined, and the operator
receives no one-time failure or recovery message.

The existing `sensor.price_watch_catalog` contract is limited to `ok` and
`degraded` and must remain backward compatible. A transient product failure
must not create email noise, while a sustained total provider failure or
incompatible Lidl product markup must be visible and actionable.

Daily-digest delivery is also visible only in the current process log. Its
last successful time, product count and promotion inclusion must survive App
restarts without changing the one-per-date reservation contract.

## Decision

Core adds a provider-neutral `core.operations` package containing immutable
operational state, deterministic transition logic, persistence and delivery
Protocols and subsystem exceptions. Core reads no clock, storage, network or
Home Assistant state.

The Home Assistant catalog application maps completed cycle evidence to one
failure kind, in priority order:

1. `CATALOG_UNAVAILABLE` when sitemap discovery failed;
2. `PROVIDER_DATA_INCOMPATIBLE` when every selected product failed data
   translation and no product succeeded;
3. `PROVIDER_UNAVAILABLE` when every selected product failed transport and no
   product succeeded;
4. `PROVIDER_FAILURE` for mixed or generic total provider failure;
5. `PARTIAL_PROVIDER_FAILURE` when failures and successes coexist;
6. `PROMOTION_UNAVAILABLE` when product/catalog work was healthy but the newly
   eligible daily promotion lookup failed;
7. no failure otherwise.

The fixed failure threshold is three consecutive failed checks. The first and
second failed checks produce `degraded`; the third produces `failed`. Further
failed checks remain `failed` without another incident notification. One
healthy check returns to `ok` and resets the counter. Failure-kind changes do
not reset the count; diagnostics describe the latest evidence while the first
failure timestamp remains the incident start.

## Durable State and Notifications

SQLite schema version 5 adds a singleton `operational_state` table containing
one versioned JSON representation. Schema 4 migrates transactionally without
changing existing rows. A missing row is the initial healthy state.

The state retains current health and failure kind, consecutive count, incident
and recovery timestamps, incident-notified state, one optional pending
notification, and the last successful daily-digest delivery metadata.

On transition to `failed`, the engine creates one pending failure notification.
Applications save it before delivery. Successful delivery is acknowledged by
a second save. Delivery failure leaves it pending for retry. Recovery creates
a notification only when the incident notification was acknowledged. Recovery
before failure delivery discards that pending message and creates no recovery
message.

Saving before delivery leaves a crash boundary: a stop after external delivery
and before acknowledgement can repeat that message. This is preferred to
permanently losing a sustained-failure warning. Channel failures are non-fatal;
persistence failures retain fatal SQLite semantics.

## Provider Error Classification

The Provider SDK adds `ProviderTransportError` and `ProviderDataError` as
subclasses of `ProviderError`. Existing consumers remain compatible. The Lidl
provider returns the transport subtype for HTTP failures and the data subtype
for product parsing or validation failures. Other providers may continue
returning `ProviderError`.

## Home Assistant Representation

Infrastructure publishes two new read-only states:

```text
sensor.price_watch_health
sensor.price_watch_daily_digest
```

Health is `ok`, `degraded` or `failed`, with cause, consecutive count,
incident timestamps, pending notification and App version attributes. The
digest state is the last successful local date or `never`, with current-cycle
status and last successful time, count and promotion flag. Digest is published
first and health last. Existing states remain unchanged.

The health attributes are exactly `friendly_name`, `failure_kind`,
`consecutive_failure_cycles`, `incident_started_at`, `last_checked_at`,
`last_recovered_at`, `incident_notified`, `pending_notification` and `version`.
Optional values use JSON null. Digest attributes are exactly `friendly_name`,
`current_status`, `last_sent_at`, `product_count`, `promotion_included` and
`version`; before the first delivery the time is null, count zero and flag
false.

Operational failure and recovery messages use the configured notify entity
and a distinct title derived from the configured notification title. They do
not consume product or digest reservations.
The exact title is `{notification_title} Operational Health`.

## Public API

`core.operations` exports `OperationalHealthStatus`,
`OperationalFailureKind`, `OperationalNotificationKind`, `OperationalCheck`,
`DailyDigestDelivery`, `OperationalState`, `OperationalNotification`,
`OperationalHealthEngine`, `OperationalStateStore`,
`OperationalNotificationChannel`, `OperationalStateError` and
`OperationalNotificationError`.

`applications.operational_monitoring` exports
`OperationalMonitoringResult` and `OperationalMonitoringWorkflow`.

`infrastructure.persistence.sqlite` exports `SqliteOperationalStateStore`.
`infrastructure.homeassistant` exports
`HomeAssistantOperationalStatusPublisher` and
`HomeAssistantOperationalNotificationChannel`. `core.provider` additionally
exports both provider-error subtypes.

Invalid public types raise `TypeError`. Invalid values and invariants raise
`ValueError`. Persistence failures raise `OperationalStateError`; delivery
failures raise `OperationalNotificationError`.

## Dependency Direction

```text
applications.homeassistant
    +--> applications.operational_monitoring
    +--> infrastructure Home Assistant and SQLite adapters

applications.operational_monitoring --> core.operations
infrastructure.persistence.sqlite --> core.operations
infrastructure.homeassistant --> core.operations
core.operations --> Python standard library only
```

## Alternatives Considered

Changing `sensor.price_watch_catalog` was rejected because it would break the
established state contract. Home Assistant-only automation state was rejected
because retry and recovery would be deployment-specific and not durable Price
Watch state. Alerting on every error was rejected as noisy. Process-memory
state was rejected because restarts would reset incidents and diagnostics.

## Consequences

The operator gets a durable, low-noise health view, one sustained-incident
email, one meaningful recovery email and restart-safe digest diagnostics.
This adds one SQLite row and two state publications per catalog cycle while
preserving product monitoring and all established public states.
