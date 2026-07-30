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

```
Scheduler
    │
    ▼
Provider
    │
    ▼
Products
    │
    ▼
History Store
    │
    ▼
Rule Engine
    │
    ▼
Notification Engine
```

---

## Responsibilities

Scheduler

- starts a cycle

Provider

- retrieves products

History Store

- loads previous state
- stores current state

Rule Engine

- evaluates rules

Notification Engine

- delivers notifications

---

## Principles

Each component performs exactly one responsibility.

Components communicate through immutable domain objects.

---

## Error Handling

A failure in one provider must not stop the entire synchronization cycle.

---

## Future Extensions

Future workflow stages may include:

- caching
- metrics
- tracing
- retries
```