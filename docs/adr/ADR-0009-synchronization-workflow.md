# ADR-0009: Synchronization Workflow

## Status

Accepted

---

## Context

The platform has independent implementations for product retrieval, previous
state storage, rule evaluation, notification generation and notification
delivery. A complete application cycle must now coordinate these components
without moving business logic or side effects into Core.

Notification delivery and JSON persistence cannot participate in one atomic
transaction. The workflow must therefore define which side effect happens
first and what a retry means after a partial failure.

---

## Decision

Application orchestration belongs to:

```text
applications.synchronization
```

The package provides a concrete `SynchronizationWorkflow`. It depends only on
existing public Core contracts and services. Concrete providers, State Store
implementations, notification channels and identifier generation are injected
at construction.

No business rule is implemented by the workflow.

---

## Public API

```python
SynchronizationWorkflow(
    providers: tuple[Provider, ...],
    state_store: StateStore,
    rule_engine: RuleEngine,
    notification_engine: NotificationEngine,
    notification_channel: NotificationChannel,
    notification_id_factory: Callable[[], UUID],
)
```

```python
run(
    rules: tuple[Rule, ...],
    timestamp: datetime,
) -> SynchronizationResult
```

`SynchronizationResult` is a frozen application result containing, in
processing order:

- successful `FetchResult` values
- all `EvaluationResult` values
- generated `Notification` values
- saved `StateSnapshot` values
- provider-reported `ProviderError` values

---

## Cycle Behavior

Providers are invoked in configured order. For each successful provider,
products are processed in fetch-result order. Every configured rule is
evaluated against every fetched product in rule order.

For each product the workflow:

1. loads the previous snapshot by product ID
2. evaluates every rule using the previous product, current product and
   caller-supplied timestamp
3. invokes `NotificationEngine.generate()` for every evaluation using an ID
   supplied by the injected factory
4. sends each generated notification through the injected channel
5. saves the current product in a `StateSnapshot` using the same timestamp

The snapshot is saved even when no rule matches. A product is saved only after
all of its generated notifications have been delivered successfully.

Rules are global in this version because the current immutable `Rule` model
contains no product selector. Rule targeting requires a separate future
Domain decision.

---

## Failure Semantics

A `ProviderError` raised by one provider is recorded and remaining providers
continue. Errors returned in `FetchResult.errors` are also recorded while the
successful products from that result are processed.

State Store, Rule Engine and notification delivery failures propagate without
translation. The workflow performs no compensation and does not conceal
unexpected programming failures.

Notification delivery precedes snapshot persistence. This prevents a failed
delivery from permanently advancing the comparison state and losing the
notification. A retry after delivery succeeded but persistence failed may
deliver the same logical notification again. Delivery is therefore
at-least-once for this version; deduplication is outside its scope.

ADR-0019 adds optional price-reference and durable reservation collaborators
without changing this default behavior. Catalog-mode price-drop alerts use the
more specific reservation-before-delivery semantics from that decision.

Any completed side effects from earlier products or providers remain
completed when a later operation fails.

---

## Determinism

The workflow does not read the system clock, generate UUIDs or access the
environment. The cycle timestamp and notification ID factory are supplied by
the caller.

Iteration order is stable and follows provider, product and rule input order.

---

## Dependency Direction

```text
Applications synchronization
    |
    +--> Core provider contract
    +--> Core State Store contract
    +--> Core Rule Engine
    +--> Core Notification Engine and channel contract
    +--> Domain
```

The workflow does not import concrete Infrastructure implementations. CLI,
Home Assistant and future applications compose those implementations at their
outer boundary.

Core and Infrastructure do not import Applications.

---

## Alternatives Considered

### Save state before notification delivery

Rejected because a delivery failure would leave the new state persisted and a
retry would no longer detect the transition that produced the notification.

### Put orchestration in Core

Rejected because the workflow invokes persistence and delivery side effects.
Core remains deterministic and side-effect free.

### Add transaction or delivery deduplication

Rejected for the first workflow because the current local JSON Store and
console channel have no shared transactional boundary or durable delivery ID
registry.

### Add product targeting to Rule

Rejected because it would change the Domain for an application composition
milestone. Global rules preserve the existing public model.

---

## Consequences

Advantages:

- one reusable complete synchronization cycle
- existing Core and Infrastructure APIs remain unchanged
- provider partial failure isolation
- explicit, deterministic ordering and inputs
- no business logic in future CLI or Home Assistant adapters

Costs:

- retries may duplicate a notification after a persistence failure
- rules currently apply to every fetched product
- a non-provider failure stops the remaining cycle without compensation
