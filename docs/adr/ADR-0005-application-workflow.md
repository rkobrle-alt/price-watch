# ADR-0005: Application Workflow

## Status

Accepted

---

## Context

The Core now contains:

- Domain
- Provider SDK
- Rule Engine

The interaction between these components must be defined before introducing persistence, scheduling and notifications.

---

## Decision

The application follows a pull-based workflow.

A scheduler triggers a synchronization cycle.

Each cycle is independent.

---

## Workflow

```text
Scheduler or application entry point
    |
    v
Provider
    |
    v
Current Products
    |
    v
State Store load
    |
    v
Rule Engine
    |
    v
Notification Engine
    |
    v
Notification Channel
    |
    v
State Store save
```

The concrete orchestration and delivery-before-persistence semantics are
defined by ADR-0009.

---

## Responsibilities

Scheduler

- starts a cycle

Provider

- retrieves products

State Store

- loads previous state
- stores current state
- uses `snapshot.product.id` as the unique storage key
- depends on caller-supplied snapshot timestamps

Rule Engine

- evaluates rules

Notification Engine

- generates notifications from evaluation results

Notification Channel

- delivers notifications

---

## Principles

Each component performs exactly one responsibility.

Components communicate through immutable domain objects.

Core defines the `StateStore` abstraction and immutable `StateSnapshot`.

Concrete State Store implementations belong to Infrastructure.

The reference implementation is located in
`infrastructure.persistence.memory`.

The durable local implementation is located in
`infrastructure.persistence.json` and follows ADR-0008.

Core defines the deterministic `NotificationEngine` and the
`NotificationChannel` Protocol.

Concrete notification channels belong to Infrastructure.
Applications compose notification generation and delivery.

---

## Error Handling

A failure in one provider must not stop the entire synchronization cycle.


State Store implementations report persistence-related failures using
`StateStoreError`.

Concrete notification channels report operational delivery failures using
`NotificationError`.

Invalid public API argument types raise `TypeError`.

`StateSnapshot` validates its own invariants. A naive snapshot timestamp raises
`ValueError`; snapshot validation does not depend on `StateStoreError`.

---

## Future Extensions

Future workflow stages may include:

- caching
- metrics
- tracing
- retries
