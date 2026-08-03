# STORY-016: SQLite Catalog and Observation Store

## Objective

Implement durable catalog membership and exact product observation history
according to ADR-0017. This story adds persistence contracts and adapters only;
it does not add the catalog monitoring workflow.

## Scope

Create:

```text
core/catalog/entry.py
core/catalog/store.py
core/state/history.py
infrastructure/persistence/snapshot_codec.py
infrastructure/persistence/sqlite/__init__.py
infrastructure/persistence/sqlite/database.py
infrastructure/persistence/sqlite/catalog_store.py
infrastructure/persistence/sqlite/state_store.py
```

Modify the corresponding public package exports and refactor the internal JSON
snapshot codec to reuse `infrastructure.persistence.snapshot_codec` without
changing JSON persistence behavior or public APIs.

Add unit tests under `tests/unit/catalog`, `tests/unit/state` and
`tests/unit/persistence`.

Do not modify Domain entities, Provider SDK, Rule Engine, Lidl provider or
catalog discovery behavior, synchronization workflow, CLI, scheduler,
notifications or Home Assistant composition.

## Core Public API

### `core.catalog`

Export:

```python
@dataclass(frozen=True, slots=True)
class CatalogEntry:
    reference: ProductReference
    first_seen_at: datetime
    last_seen_at: datetime
```

Validation:

- `reference` must be `ProductReference`
- timestamps must be `datetime` instances and timezone-aware
- `last_seen_at` must not precede `first_seen_at`
- invalid types raise `TypeError`; invalid values raise `ValueError`

Export:

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

Export `CatalogStoreError`, deriving from `Exception`, for catalog-persistence,
schema and persisted-data failures. Existing `CatalogError` remains the
discovery failure type and is not changed or reused for persistence.

### `core.state`

Export:

```python
class ObservationHistory(Protocol):
    def history(
        self,
        product_id: ProductId,
        limit: int | None = None,
    ) -> tuple[StateSnapshot, ...]: ...
```

The existing `StateStore`, `StateSnapshot` and `StateStoreError` APIs remain
unchanged.

## Infrastructure Public API

### `infrastructure.persistence.sqlite`

Export:

```python
SqliteCatalogStore(
    path: Path,
    timeout_seconds: int = 5,
)

SqliteStateStore(
    path: Path,
    timeout_seconds: int = 5,
)
```

Construction performs validation only. `path` must be exactly a `Path` and
`timeout_seconds` must be a positive integer that rejects `bool`. Construction
must not create a directory, database or connection.

The two objects may receive the same path and must interoperate through the
same version-1 schema.

## Catalog Store Behavior

`record_discovery()` validates the complete call before any persistence:

- `references` must be a tuple containing only `ProductReference` values
- duplicate `(provider_id, external_id)` identities raise `ValueError`
- `discovered_at` must be a timezone-aware `datetime`
- an empty tuple is accepted and returns an empty tuple

Within one transaction and in input order:

- a new identity is inserted with equal first- and last-seen timestamps
- an existing identity preserves `first_seen_at`, replaces its URL with the
  supplied canonical URL and advances `last_seen_at`
- a timestamp earlier than any affected existing `last_seen_at` raises
  `ValueError` and rolls back every change from that call

The return value contains only newly inserted references in input order.

`list_entries(provider_id)` accepts only `ProviderId` and returns every stored
entry for that provider in stable insertion order. Unknown providers return an
empty tuple. Persisted UUIDs, strings and timestamps are decoded through Core
constructors; malformed persisted data raises `CatalogStoreError` with cause.

Entries omitted by later discovery calls are not deleted or modified.

## State and History Behavior

`SqliteStateStore` structurally implements both `StateStore` and
`ObservationHistory`.

- `save(snapshot)` accepts only `StateSnapshot` and appends one observation
- every save is retained, including identical and unchanged snapshots
- `load(product_id)` returns the last inserted observation for that product
- an unknown product returns `None`
- `history(product_id)` returns all observations oldest to newest
- `history(product_id, limit)` returns the newest `limit` observations, still
  ordered oldest to newest
- `limit` accepts `None` or a positive `int` and rejects `bool`

Each observation round-trips the complete immutable Product and snapshot
timestamp exactly. Money and percentages never pass through `float`.

SQLite, schema, JSON decoding and persisted invariant failures raise
`StateStoreError` with cause. Invalid public arguments retain `TypeError` or
`ValueError` and are not wrapped.

## Shared Snapshot Codec

Move the representation-independent snapshot encode/decode behavior from the
JSON package into the private module:

```text
infrastructure.persistence.snapshot_codec
```

The JSON document schema remains in `infrastructure.persistence.json.codec`.
Its encoded document, schema version, deterministic formatting, error
semantics and internal test compatibility must remain unchanged.

The SQLite observation payload uses deterministic compact JSON produced from
the same encoded snapshot mapping. Decoding must call the same shared decoder
and enforce that the indexed product ID matches the decoded Product ID.

The shared codec is Infrastructure-internal and is not exported from
`infrastructure.persistence`.

## Schema and Transactions

Use Python's standard-library `sqlite3`; add no dependency.

Version 1 uses `PRAGMA user_version = 1` and these logical tables:

- `catalog_entries`: integer insertion sequence, provider UUID, external ID,
  URL, first-seen timestamp and last-seen timestamp; provider/external ID is
  unique
- `observations`: integer insertion sequence, product UUID and encoded exact
  snapshot; product UUID plus insertion sequence is indexed

The first public operation:

1. creates missing parent directories
2. opens the explicit database path with the configured timeout
3. initializes schema version 1 transactionally only when no user tables exist

Every connection is closed after the operation. Every write operation is
transactional. Catalog timestamp rejection must roll back the complete batch.

Reject with the relevant subsystem error:

- unversioned databases containing user tables
- any `user_version` other than 1 after initialization
- missing or incompatible Price Watch tables
- database open, locking, query, commit or close-related SQLite failures

Do not delete, compact or prune observations or catalog entries.

## Architecture Boundaries

Core may depend only on public Core packages and the standard library. It must
not import SQLite, JSON, filesystem, Infrastructure or Applications.

`infrastructure.persistence.sqlite` may depend on public `core.catalog`,
`core.domain`, `core.state`, the private shared snapshot codec and standard
library modules. It must not import providers, rules, notifications,
Applications, HTTP or Home Assistant.

No product pages are fetched and no clocks, UUIDs or global state are read.

## Unit Tests

Cover:

- all immutable `CatalogEntry` validations and equality
- structural compatibility of both new Protocols and exception hierarchy
- constructor validation and proof that construction performs no I/O
- schema creation, exact version and coexistence of both SQLite stores
- new, repeated, URL-changing, empty, mixed-provider and duplicate discovery
- stable ordering, first/last-seen behavior and complete rollback on stale time
- exact Product and snapshot round-trip, duplicate observation retention,
  last-write-wins loading, history ordering and limits
- missing database, unknown identities and multiple reopened store instances
- malformed snapshot payloads, malformed catalog rows, unknown versions,
  unversioned foreign tables and operational SQLite failures with chaining
- JSON State Store regression behavior after codec extraction
- public exports and dependency boundaries

Tests must use temporary local databases or injected failures and must never
access the network.

## Acceptance Criteria

- ADR-0017 public APIs and semantics are implemented exactly
- existing JSON and in-memory State Stores remain backward compatible
- existing discovery and application behavior remains unchanged
- catalog batches and observation saves are atomic
- exact monetary data is preserved without `float`
- no history is deleted automatically
- every public object has type hints and a docstring
- all public APIs are exported through `__init__.py`
- no TODOs, placeholders, `pass`, skipped tests, commented-out code or dead code
- the complete suite passes with 100 percent statement and branch coverage
