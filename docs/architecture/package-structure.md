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

    catalog/

    provider/

    rules/

    state/

    notifications/

    scheduler/

    configuration/
```

The Core contains only business logic.

The Core must not perform I/O.

The Core defines public abstractions (Protocols), domain models and business services.

Concrete implementations belong to Infrastructure.

For discovery, `core.catalog` contains only the immutable `ProductReference`,
`ProductCatalog` Protocol and `CatalogError` contract from ADR-0016. It
contains no HTTP, XML, gzip or Lidl-specific code. ADR-0017 adds the immutable
`CatalogEntry`, `CatalogStore` Protocol and `CatalogStoreError` persistence
boundary without adding a concrete store to Core.

For product state, `core.state` contains only:

- the `StateStore` Protocol
- the immutable `StateSnapshot`
- the `StateStoreError` persistence-failure contract
- the read-only `ObservationHistory` Protocol

It contains no concrete State Store implementation.

For notifications, `core.notifications` contains:

- the deterministic `NotificationEngine`
- the `NotificationChannel` Protocol
- the `NotificationError` delivery-failure contract
- the immutable notification reservation identity
- the reservation-store Protocol and persistence-error contract
- the deterministic price-drop reservation policy

It contains no concrete notification channel.

For scheduling, `core.scheduler` contains only:

- the `Delay` Protocol
- the `SchedulerError` operational-failure contract

It does not read time, sleep, start threads or orchestrate applications.

For application configuration, `core.configuration` contains only the
`ConfigurationLoader` Protocol and `ConfigurationError` contract defined by
ADR-0012. It contains no file-format parser or filesystem access.

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

        homeassistant/

    homeassistant/

    http/

    scheduler/

    configuration/

        toml/

        json/
```

Infrastructure contains all external integrations and concrete implementations.

`infrastructure.providers.lidl` contains the first provider implementation for
explicitly configured Lidl Czech Republic Parkside product pages. ADR-0016
adds a separate sitemap catalog implementation which discovers references
without changing the existing product provider.

`infrastructure.http` contains the injectable text HTTP boundary and its
standard-library reference implementation. ADR-0016 adds an independently
bounded binary HTTP boundary for compressed sitemap retrieval.

`infrastructure.persistence.memory` contains the reference
`InMemoryStateStore` implementation.

`infrastructure.persistence.json` contains the durable, versioned
`JsonStateStore` implementation for local filesystem persistence.

`infrastructure.persistence.sqlite` contains the versioned catalog-scale
`SqliteCatalogStore` and `SqliteStateStore` implementations from ADR-0017.
They may share one database while satisfying separate Core contracts. The
SQLite State Store appends exact observations and remains compatible with the
latest-snapshot `StateStore` contract. ADR-0018 extends the catalog adapter
with durable refresh ordering and migrates valid schema version 1 databases to
version 2. No retention deletion is automatic.
ADR-0019 adds `SqliteNotificationReservationStore` and migrates valid schema
version 2 databases to version 3 while preserving catalog and observation
data. Valid version 1 databases migrate sequentially through both steps.
ADR-0020 adds `SqliteDailyDigestReservationStore`, latest-snapshot collection
queries and the sequential schema version 3 to 4 migration.

`infrastructure.persistence.snapshot_codec` is a private shared codec used by
JSON and SQLite persistence. It preserves exact Domain values and is not a
public package API.

`infrastructure.notifications.console` contains the reference
`ConsoleNotificationChannel` implementation.

Concrete notification channels own delivery side effects.
`infrastructure.notifications.homeassistant` delegates notification delivery
to an explicit Home Assistant notify entity according to ADR-0013.

`infrastructure.homeassistant` contains the Home Assistant service-call
contract, operational error and standard-library REST client. It stores no
credentials and imports no Applications. It also contains the state-update
contract and deterministic status publisher defined by ADR-0015. The publisher
accepts Domain products and explicit cycle values; it does not own monitoring
business logic.

`infrastructure.scheduler` contains `SystemDelay`, the standard-library
implementation of the Core delay boundary.

`infrastructure.configuration.toml` contains the explicit UTF-8 TOML file
loader. `infrastructure.configuration.json` loads Home Assistant App options.
Both perform decoding only; application-schema validation remains in
Applications.

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

    catalog_monitoring/

    daily_digest/

    synchronization/

    scheduler/

    configuration/

    cli/

    api/

    homeassistant/
```

Applications compose the system.

They configure dependencies and execute workflows.

`applications.catalog_monitoring` contains the bounded discovery and refresh
orchestration from ADR-0018. It depends on public catalog contracts and an
injected batch synchronizer which reuses `applications.synchronization`. It
does not construct Lidl, SQLite or Home Assistant implementations.

`applications.synchronization` contains the reusable synchronization
orchestration defined by ADR-0009. It depends on public Core contracts and
services, while concrete Infrastructure implementations are injected by outer
application entry points. ADR-0019 adds optional observation enrichment and
logical price-alert reservation collaborators without changing default callers.

`applications.scheduler` contains the reusable fixed-delay interval
orchestration defined by ADR-0011. It invokes an injected cycle serially and
depends on the Core delay abstraction.

`applications.configuration` contains the immutable application configuration
and pure schema validation defined by ADR-0012. It performs no file I/O.

`applications.cli` is the first executable composition root. It parses explicit
process arguments, supplies clock and UUID generation, composes the Lidl/JSON/
console stack and invokes `applications.synchronization` according to ADR-0010.
Its `watch` command composes the interval scheduler and Infrastructure delay
according to ADR-0011. Configuration-file commands compose the pure
Application parser with the Infrastructure TOML loader according to ADR-0012.
`applications.homeassistant` is the Supervisor-managed composition root defined
by ADR-0014. It loads App options, injects Supervisor access at the process
boundary, uses persistent `/data` state, composes Home Assistant notification
delivery and runs the existing serial scheduler. According to ADR-0015 it also
publishes completed-cycle and product state representations through the same
injected Home Assistant REST client. ADR-0018 adds an opt-in catalog mode that
composes sitemap discovery and shared SQLite persistence while preserving the
explicit URL/JSON mode for existing option documents.
ADR-0019 enables historical 20-percent evaluation and durable alert
reservations only in that catalog composition.
`applications.daily_digest` contains deterministic calendar eligibility and
orchestration over injected Core contracts. ADR-0020 composes it only in Home
Assistant catalog mode when explicitly enabled.

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
