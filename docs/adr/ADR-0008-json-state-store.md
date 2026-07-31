# ADR-0008: JSON State Store

## Status

Accepted

---

## Context

The in-memory State Store loses every product snapshot when a process exits.
The Rule Engine therefore cannot compare current products with state captured
by an earlier execution.

The first durable implementation must preserve the existing `StateStore`
contract, keep filesystem access in Infrastructure and remain simple enough
for local execution and the future CLI application.

---

## Decision

The first durable State Store implementation is:

```text
infrastructure.persistence.json.JsonStateStore
```

Its constructor receives one explicit `pathlib.Path` identifying a JSON file.
Construction performs no filesystem access.

The store implements the existing `core.state.StateStore` Protocol without
changing Core or Domain public APIs.

---

## Storage Model

One JSON document stores the latest snapshot for every product.

The document contains:

```json
{
  "schema_version": 1,
  "snapshots": {
    "<product UUID>": {
      "product": {},
      "timestamp": "<timezone-aware ISO 8601>"
    }
  }
}
```

The unique key is `snapshot.product.id.value` encoded as its canonical UUID
string. Saving an existing key replaces the previous snapshot regardless of
timestamp, preserving the last-write-wins semantics from STORY-004.

The schema version is mandatory. Unsupported versions are rejected rather
than interpreted silently.

---

## Domain Encoding

The complete immutable `Product` is persisted so it can be reconstructed
without a provider call.

Encoding rules:

- UUID values use canonical strings
- `Decimal` values use strings and are never converted through `float`
- enum values use their public string values
- timezone-aware datetimes use `datetime.isoformat()`
- optional values use JSON `null`
- booleans remain JSON booleans

Loading reconstructs Domain value objects, `Product` and `StateSnapshot` so
their existing invariant validation remains authoritative.

The internal codec belongs to Infrastructure and is not a public API.

---

## File Behavior

A missing JSON file represents an empty store. `load()` returns `None` for an
unknown product.

On the first `save()`, missing parent directories are created.

Every save:

1. reads and validates the existing document when present
2. replaces or adds one snapshot in memory
3. writes a uniquely named temporary file in the destination directory
4. flushes and synchronizes the temporary file
5. atomically replaces the destination using `os.replace`

If replacement fails, the existing destination remains unchanged and the
temporary file is removed when possible.

JSON output is UTF-8, deterministic, human-readable and ends with one newline.

---

## Error Handling

Invalid public argument types raise `TypeError`:

- constructor `path` must be `pathlib.Path`
- `load()` requires `ProductId`
- `save()` requires `StateSnapshot`

Persistence-related failures raise `StateStoreError` with the original
exception preserved as the cause. These include:

- filesystem access failures
- invalid UTF-8 or malformed JSON
- invalid document structure or schema version
- invalid persisted UUID, Decimal, enum or datetime values
- persisted values that violate Domain or snapshot invariants
- a storage key that differs from the decoded product identifier

`StateStoreError` is not used for invalid public argument types.

---

## Concurrency

The first version provides atomic replacement but no cross-process locking or
conflict detection.

Applications must not share one JSON file between concurrent writers.
Multi-process coordination requires a separate future decision.

---

## Dependency Direction

`infrastructure.persistence.json` may depend on:

- the public `core.domain` API
- the public `core.state` API
- Python standard library filesystem and JSON modules

Core must not import the JSON implementation.

The implementation must not depend on providers, rules, notifications,
Applications, Home Assistant, HTTP or databases.

---

## Alternatives Considered

### One JSON file per product

Rejected for the first version because it adds directory lifecycle and partial
collection management without a current scale requirement.

### Append-only event log

Rejected because STORY-004 requires only the latest snapshot and no history or
replay semantics have been approved.

### Directly overwrite the destination file

Rejected because interruption during a write could destroy the previously
valid state.

### Add serialization methods to Domain objects

Rejected because JSON is an Infrastructure representation and must not leak
into Domain or Core.

---

## Consequences

Advantages:

- state survives process restarts
- existing State Store and Domain APIs remain unchanged
- writes protect the previous file through atomic replacement
- the format preserves exact monetary values
- schema evolution is explicit

Costs:

- each operation reads or writes the complete document
- concurrent writers are unsupported
- future Domain changes may require a new schema version and migration policy
