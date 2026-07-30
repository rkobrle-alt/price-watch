# STORY-004 – State Store

## Goal

Implement the abstraction responsible for loading and storing the latest product state.

The implementation must remain independent of persistence technology.

---

## Public API

Package:

core.state

Public types:

- StateStore
- StateSnapshot
- StateStoreError

Core contains the State Store abstraction and snapshot model only.

Concrete State Store implementations belong to Infrastructure.

---

## StateStore

Use `typing.Protocol`.

Methods:

```python
load(product_id: ProductId) -> StateSnapshot | None

save(snapshot: StateSnapshot) -> None
```

The store is responsible for loading and storing the latest snapshot of a product.

Invalid argument types passed to `load()` or `save()` raise `TypeError`.

---

## StateSnapshot

Frozen dataclass.

Fields:

- product: Product
- timestamp: datetime

Rules:

- `product` must be a `Product`; any other type raises `TypeError`.
- `timestamp` must be a `datetime`; any other type raises `TypeError`.
- `timestamp` must be timezone-aware.
- A naive `timestamp` raises `ValueError`.
- `timestamp` is supplied by the caller.
- The Core must not obtain the current time itself.
- `StateSnapshot` validates these invariants itself.
- `StateSnapshot` must not depend on `StateStoreError`.

---

## Save Semantics

Saving a snapshot with an existing `ProductId` replaces the previous snapshot.

The unique storage key is `snapshot.product.id`.

The State Store always keeps only the latest snapshot for each product.

Timestamp ordering is not evaluated in this version.

Conflict resolution is out of scope.

The timestamp is stored as snapshot metadata only.

It is not used to decide whether a snapshot should replace an existing one.

---

## InMemoryStateStore

Reference implementation.

Package:

`infrastructure.persistence.memory`

Class:

`InMemoryStateStore`

Public import:

```python
from infrastructure.persistence.memory import InMemoryStateStore
```

Intended for:

- unit tests
- local execution

Characteristics:

- stores snapshots in memory only
- no file I/O
- no database
- no HTTP

---

## StateStoreError

Base exception for State Store implementations.

State Store implementations raise `StateStoreError` only for
persistence-related failures.

The reference `InMemoryStateStore` is not expected to raise this exception during normal operation.

`StateStoreError` is not used for invalid argument types or
`StateSnapshot` invariant violations.

---

## Rules

The Core must remain deterministic.

The implementation must not depend on:

- filesystem
- database
- network
- environment variables
- system clock

---

## Tests

Cover:

- save
- load
- overwrite existing snapshot
- last write wins
- unknown product returns `None`
- snapshot immutability
- `StateSnapshot` with a non-`Product` product raises `TypeError`
- non-`datetime` timestamp raises `TypeError`
- naive timestamp raises `ValueError`
- invalid `load()` and `save()` argument types raise `TypeError`
- timezone-aware timestamp validation
- snapshots are keyed by `snapshot.product.id`
- `core.state` public API exports
- `infrastructure.persistence.memory` public API export

Target:

- 100% test coverage