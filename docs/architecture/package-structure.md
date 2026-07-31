# Package Structure

This document defines the long-term package organization of Price Watch.

The structure follows the principles of Clean Architecture.

The Core defines business models and abstractions.

Infrastructure provides concrete implementations.

Applications compose the system.

---

# Core

```
core/

    domain/

    provider/

    rules/

    state/

    notifications/

    scheduler/
```

The Core contains only business logic.

The Core must not perform I/O.

The Core defines public abstractions (Protocols), domain models and business services.

Concrete implementations belong to Infrastructure.

For product state, `core.state` contains only:

- the `StateStore` Protocol
- the immutable `StateSnapshot`
- the `StateStoreError` persistence-failure contract

It contains no concrete State Store implementation.

For notifications, `core.notifications` contains:

- the deterministic `NotificationEngine`
- the `NotificationChannel` Protocol
- the `NotificationError` delivery-failure contract

It contains no concrete notification channel.

For scheduling, `core.scheduler` contains only:

- the `Delay` Protocol
- the `SchedulerError` operational-failure contract

It does not read time, sleep, start threads or orchestrate applications.

---

# Infrastructure

```
infrastructure/

    providers/

        lidl/

    persistence/

        memory/

        json/

        sqlite/

    notifications/

        console/

        email/

        telegram/

        discord/

    http/

    scheduler/
```

Infrastructure contains all external integrations and concrete implementations.

`infrastructure.providers.lidl` contains the first provider implementation for
explicitly configured Lidl Czech Republic Parkside product pages.

`infrastructure.http` contains the injectable text HTTP boundary and its
standard-library reference implementation.

`infrastructure.persistence.memory` contains the reference
`InMemoryStateStore` implementation.

`infrastructure.persistence.json` contains the durable, versioned
`JsonStateStore` implementation for local filesystem persistence.

`infrastructure.notifications.console` contains the reference
`ConsoleNotificationChannel` implementation.

Concrete notification channels own delivery side effects.

`infrastructure.scheduler` contains `SystemDelay`, the standard-library
implementation of the Core delay boundary.

Infrastructure is responsible for:

- persistence
- network communication
- notification delivery
- filesystem access
- external APIs

---

# Applications

```
applications/

    synchronization/

    scheduler/

    cli/

    api/

    homeassistant/
```

Applications compose the system.

They configure dependencies and execute workflows.

`applications.synchronization` contains the reusable synchronization
orchestration defined by ADR-0009. It depends on public Core contracts and
services, while concrete Infrastructure implementations are injected by outer
application entry points.

`applications.scheduler` contains the reusable fixed-delay interval
orchestration defined by ADR-0011. It invokes an injected cycle serially and
depends on the Core delay abstraction.

`applications.cli` is the first executable composition root. It parses explicit
process arguments, supplies clock and UUID generation, composes the Lidl/JSON/
console stack and invokes `applications.synchronization` according to ADR-0010.
Its `watch` command composes the interval scheduler and Infrastructure delay
according to ADR-0011.

---

# Tests

```
tests/

    unit/

        domain/

        provider/

        rules/

        state/

        notifications/

    integration/
```

Unit tests never require network access.

Integration tests may access external systems.

---

# Dependency Rules

Applications â†’ Infrastructure â†’ Core

Dependencies always point toward the Core.

The Core must never depend on Infrastructure or Applications.

---

# Public API

Every package exports its public API through:

```
__init__.py
```

Internal modules remain private.

---

# Naming

Packages use:

```
lowercase
```

Classes use:

```
PascalCase
```

Functions use:

```
snake_case
```

Constants use:

```
UPPER_CASE
```
