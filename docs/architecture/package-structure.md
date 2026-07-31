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
