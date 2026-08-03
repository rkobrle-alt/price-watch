# ADR-0017: SQLite Catalog and Observation Store

## Status

Accepted

Schema version 1 remains the historical base schema. ADR-0018 defines the
accepted transactional migration to current schema version 2 and supersedes
only the earlier rejection of every version other than 1.

---

## Context

ADR-0016 discovers immutable Parkside product references but intentionally
performs no persistence. Catalog-scale monitoring needs durable membership,
exact price and availability observations and compatibility with the existing
latest-snapshot `StateStore` contract.

The JSON State Store rewrites one complete document for every product update.
That remains appropriate for explicitly configured products, but it is not an
appropriate history representation for a catalog containing thousands of
products. The next persistence boundary must remain independent of Lidl,
workflow scheduling and Home Assistant.

---

## Decision

Core adds provider-neutral catalog persistence abstractions and a read-only
observation-history abstraction. Concrete SQLite implementations belong to
Infrastructure.

The durable implementations are:

```text
infrastructure.persistence.sqlite.SqliteCatalogStore
infrastructure.persistence.sqlite.SqliteStateStore
```

Both accept the same explicit `pathlib.Path` when they must share one database.
Construction validates configuration but performs no filesystem or database
access.

---

## Core Catalog Contracts

`core.catalog` exports:

```python
@dataclass(frozen=True, slots=True)
class CatalogEntry:
    reference: ProductReference
    first_seen_at: datetime
    last_seen_at: datetime
```

Both timestamps must be timezone-aware and `last_seen_at` must not precede
`first_seen_at`.

```python
class CatalogStore(Protocol):
    def record_discovery(
        self,
        references: tuple[ProductReference, ...],
        discovered_at: datetime,
    ) -> tuple[ProductReference, ...]: ...

    def list_entries(
        self,
        provider_id: ProviderId,
    ) -> tuple[CatalogEntry, ...]: ...
```

`record_discovery()` is atomic. It inserts new identities, preserves their
first-seen time, updates their canonical URL and last-seen time on subsequent
discoveries and returns only newly inserted references in input order. An
empty tuple is valid and makes no membership changes. Duplicate
`(provider_id, external_id)` identities in one call raise `ValueError`.

A discovery timestamp earlier than an existing entry's last-seen timestamp is
rejected with `ValueError`, and the complete call is rolled back. This prevents
chronology from depending silently on call order.

`list_entries()` returns every retained entry for one provider in stable first
insertion order. Entries not present in a later discovery are retained with
their previous `last_seen_at`; lifecycle policy belongs to a later workflow.

`CatalogStoreError` reports persistence, schema and persisted-data failures.
Invalid public argument types raise `TypeError`; invalid values raise
`ValueError` and are not wrapped.

---

## Observation History Contract

`core.state` adds:

```python
class ObservationHistory(Protocol):
    def history(
        self,
        product_id: ProductId,
        limit: int | None = None,
    ) -> tuple[StateSnapshot, ...]: ...
```

The returned snapshots use insertion order from oldest to newest. When
`limit` is supplied, the most recent `limit` observations are returned while
preserving that chronological order. A limit must be a positive integer and
must reject `bool`.

`SqliteStateStore` implements both the unchanged `StateStore` Protocol and the
new `ObservationHistory` Protocol. Every successful `save()` appends one exact
observation. `load()` returns the most recently saved observation by insertion
sequence, preserving existing last-write-wins behavior even when caller-
supplied timestamps are equal or out of order.

All complete immutable `Product` fields and the snapshot timestamp are
retained. UUID, `Decimal`, enum and timezone-aware datetime values use the same
lossless representation as the JSON State Store. A shared private
Infrastructure snapshot codec is used so the two stores cannot drift.

---

## SQLite Schema and Initialization

Schema version 1 uses SQLite `PRAGMA user_version` and contains:

- `catalog_entries`, with insertion sequence and a unique provider/external ID
- `observations`, with insertion sequence, indexed product ID and an exact
  encoded snapshot

The schema is initialized transactionally on the first operation when the
database contains no application tables. A database with unrecognized tables
and no Price Watch version is rejected. A schema version newer than or
otherwise different from version 1 is rejected rather than interpreted or
overwritten.

Future migrations must be explicit, sequential and transactional. Version 1
has no predecessor requiring a data migration.

Each public operation uses a transaction and closes its connection. SQLite
locking or I/O failures retain their subsystem error boundary:

- catalog operations raise `CatalogStoreError`
- latest-state and observation operations raise `StateStoreError`

No cross-process application scheduler coordination is introduced. SQLite
serializes writes; Applications must still avoid overlapping monitoring
cycles according to ADR-0011.

---

## Retention

Version 1 performs no automatic deletion or compaction. Catalog entries and
observations are retained indefinitely so a default limit cannot silently
destroy user history. A future retention policy is an intentional data-
lifecycle decision and requires documentation and migration behavior before
implementation.

---

## Dependency Direction

```text
future Applications catalog workflow
    +--> core.catalog CatalogStore
    +--> core.state StateStore and ObservationHistory
    +--> injected Infrastructure implementations

infrastructure.persistence.sqlite
    +--> core.catalog
    +--> core.state
    +--> core.domain
    +--> Python standard library sqlite3 and filesystem APIs
```

Core imports neither SQLite nor Infrastructure. SQLite persistence imports no
provider implementation, Applications, rules, notifications, HTTP or Home
Assistant.

---

## Compatibility

The JSON and in-memory State Stores remain unchanged and supported. Existing
CLI and Home Assistant composition continues using JSON until a later workflow
ADR intentionally adopts catalog monitoring. Domain entities, the Provider
SDK, Rule Engine and `LidlParksideProvider` public APIs do not change.

---

## Alternatives Considered

### Extend the JSON State Store with arrays of history

Rejected because every observation would rewrite an increasingly large
document and catalog queries would require decoding all products.

### Store only changed prices or availability

Deferred because it would change observation semantics and discard evidence
that a product was checked but unchanged. Version 1 records every successful
save exactly.

### Apply a default retention count

Rejected because any arbitrary count silently deletes user data and depends on
a refresh frequency not yet approved by the catalog workflow.

### Replace the existing StateStore contract

Rejected because latest-state consumers remain valid. The SQLite adapter can
provide history while satisfying the established contract unchanged.

---

## Consequences

Advantages:

- catalog-scale indexed persistence without changing Domain
- exact, ordered and durable observation history
- unchanged latest-snapshot workflow compatibility
- atomic catalog discovery batches and deterministic new-reference reporting
- explicit schema evolution and no silent data loss

Costs:

- two adapters coordinate through one shared SQLite schema
- storage grows until a future retention policy is approved
- catalog discovery and product refresh remain separate workflow steps
