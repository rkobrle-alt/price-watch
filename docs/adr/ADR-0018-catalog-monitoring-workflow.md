# ADR-0018: Catalog Monitoring Workflow

## Status

Accepted

---

## Context

ADR-0016 discovers Parkside product references and ADR-0017 persists catalog
membership and observations. The platform still has no application workflow
which turns the durable catalog into bounded product-page refreshes.

Selecting the first retained entries on every cycle would starve later
products, especially after process restarts. Observation history cannot solve
this because a discovery `external_id` is not the Domain `ProductId` derived
later from page JSON-LD. Refresh-attempt order must therefore be persisted at
the catalog identity boundary.

The existing explicit-URL synchronization workflow, Rule Engine,
notification ordering and Provider SDK remain authoritative and must be
reused.

---

## Decision

Core adds a provider-neutral catalog-refresh persistence contract.
Infrastructure SQLite implements that contract through an explicit schema
migration. A new Application workflow coordinates discovery and bounded
synchronization without implementing provider, rule or notification logic.

The reusable workflow belongs to:

```text
applications.catalog_monitoring
```

The Home Assistant App gains an opt-in catalog mode. Existing App options
without that mode retain explicit URL monitoring and JSON persistence.

---

## Core Refresh Contract

`core.catalog` exports:

```python
class CatalogRefreshStore(Protocol):
    def list_refresh_batch(
        self,
        provider_id: ProviderId,
        limit: int,
    ) -> tuple[ProductReference, ...]: ...

    def record_refresh_attempt(
        self,
        references: tuple[ProductReference, ...],
        attempted_at: datetime,
    ) -> None: ...
```

`list_refresh_batch()` returns at most `limit` retained references. References
without a recorded attempt come first in catalog insertion order. Remaining
references follow from oldest attempt to newest, using catalog insertion order
as the stable tie-breaker.

`record_refresh_attempt()` is atomic, requires unique retained identities and
rejects a timestamp earlier than an affected existing attempt. An empty tuple
is valid. Invalid types raise `TypeError`, invalid values raise `ValueError`
and persistence failures raise `CatalogStoreError`.

The existing `CatalogEntry` and `CatalogStore` APIs do not change.

---

## SQLite Migration

SQLite schema version 2 adds nullable `last_refresh_attempt_at` to
`catalog_entries` and an index supporting refresh ordering.

Opening a valid version-1 Price Watch database migrates it transactionally to
version 2. Every existing entry receives a null attempt and is therefore
eligible for initial refresh. Version 2 is validated exactly. Unknown,
unversioned or future schemas remain rejected.

Both `SqliteCatalogStore` and `SqliteStateStore` open and validate version 2.
Observation representation and history semantics do not change.

---

## Application Public API

`applications.catalog_monitoring` exports:

```python
class CatalogBatchSynchronizer(Protocol):
    def synchronize(
        self,
        references: tuple[ProductReference, ...],
        rules: tuple[Rule, ...],
        timestamp: datetime,
    ) -> SynchronizationResult: ...
```

```python
@dataclass(frozen=True, slots=True)
class CatalogMonitoringResult:
    discovered_references: tuple[ProductReference, ...]
    new_references: tuple[ProductReference, ...]
    refresh_references: tuple[ProductReference, ...]
    synchronization: SynchronizationResult | None
    catalog_error: CatalogError | None
```

```python
CatalogMonitoringWorkflow(
    catalog: ProductCatalog,
    catalog_store: CatalogStore,
    refresh_store: CatalogRefreshStore,
    batch_synchronizer: CatalogBatchSynchronizer,
    provider_id: ProviderId,
    batch_size: int,
)
```

```python
run(
    rules: tuple[Rule, ...],
    timestamp: datetime,
    discover: bool = True,
) -> CatalogMonitoringResult
```

The batch synchronizer is an Application boundary because it returns the
existing Application `SynchronizationResult`. Concrete provider and channel
composition remains in the outer application.

---

## Cycle Behavior

When `discover` is true, one cycle:

1. invokes `ProductCatalog.discover()`
2. records the complete discovery with the supplied timestamp
3. retains any `CatalogError` and continues with already persisted entries
4. selects one bounded refresh batch
5. invokes the injected batch synchronizer once when the batch is non-empty
6. records a refresh attempt for the complete batch after synchronization
   returns, including a result containing provider errors

When discovery fails, no partial discovery is recorded. When a non-provider
synchronization failure propagates, the attempt is not recorded and the batch
is eligible for retry. Empty catalogs produce a result without
synchronization.

Newly discovered references are eligible in the same cycle and have priority.
The batch limit remains authoritative during first bootstrap, so a large
catalog cannot cause an unbounded product-page burst. Pending new references
continue to have priority on later cycles.

All processing is serial. The existing interval scheduler guarantees that
cycles do not overlap.

---

## Home Assistant Adoption

Home Assistant App options add:

- `catalog_enabled`, boolean, treated as false when absent
- `catalog_batch_size`, positive integer, default 25
- `catalog_discovery_interval_cycles`, positive integer, default 288

In explicit mode, `product_urls` remains required and the App keeps
`/data/state.json`. In catalog mode, `product_urls` is ignored if absent and
the App uses `/data/catalog.sqlite3` for both catalog and observations.

The packaged defaults enable catalog mode for new installations. Existing
installed option documents do not acquire the key automatically at parsing
time and therefore remain backward compatible.

The first catalog cycle performs discovery. Later discovery occurs every
configured number of cycles; every cycle refreshes one batch. Restarting the
App performs discovery immediately. This cadence is Application scheduling,
not Core business logic.

Catalog discovery failures are reported and counted like provider-error
cycles but do not stop later cycles. Catalog persistence, Rule Engine,
notification and scheduler failures retain their subsystem boundaries and
stop execution. Status publication uses the products actually refreshed in
that cycle.

The CLI remains on explicit URL monitoring in this milestone. It is unchanged
and continues to use JSON persistence.

---

## Dependency Direction

```text
applications.homeassistant
    +--> applications.catalog_monitoring
    +--> applications.synchronization
    +--> Infrastructure composition

applications.catalog_monitoring
    +--> core.catalog
    +--> core.domain
    +--> applications.synchronization result

infrastructure.persistence.sqlite
    +--> core.catalog
    +--> core.state
```

Core imports neither Applications nor Infrastructure. The reusable catalog
workflow imports no concrete Lidl, SQLite or Home Assistant implementation.

---

## Alternatives Considered

### Keep an in-memory rotating offset

Rejected because every restart would begin at the first catalog entry and
could repeatedly starve later products.

### Derive refresh order from observation history

Rejected because discovery identity and Domain product identity are distinct
until a product page has been parsed, and failed candidates may have no
observation.

### Refresh every newly discovered reference without a limit

Rejected because the first catalog bootstrap could issue thousands of product
page requests in one cycle.

### Replace the existing synchronization workflow

Rejected because its provider isolation, delivery ordering, rule evaluation
and state persistence are already authoritative and reusable.

---

## Consequences

Advantages:

- bounded and restart-safe catalog rotation
- immediate same-cycle priority for newly discovered products
- reuse of existing synchronization and notification behavior
- continued monitoring when sitemap discovery temporarily fails
- backward-compatible explicit URL mode

Costs:

- one explicit SQLite schema migration
- catalog refresh cadence adds Home Assistant options
- a failed product page is retried only after the remaining catalog rotates
- CLI catalog commands remain deferred
