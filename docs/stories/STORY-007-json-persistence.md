# STORY-007: JSON Persistence

## Goal

Implement the first durable `StateStore` using a versioned JSON file according
to ADR-0008.

The implementation must preserve the existing Domain and `core.state` public
APIs.

---

## Package Structure

Create:

```text
infrastructure/persistence/json/
    __init__.py
    codec.py
    store.py

tests/unit/persistence/
    __init__.py
    helpers.py
    test_architecture.py
    test_codec_failures.py
    test_json_state_store.py
    test_public_api.py
```

---

## Public API

Export through `infrastructure.persistence.json`:

- `JsonStateStore`

Every public object must have explicit type hints and a docstring.

The codec, document schema and filesystem helpers remain internal.

---

## JsonStateStore

Constructor:

```python
__init__(path: Path) -> None
```

Requirements:

- `path` must be exactly a `pathlib.Path` instance or subclass
- an invalid type raises `TypeError`
- construction performs no filesystem access
- the path is retained without resolving it or reading environment state

The class structurally implements `core.state.StateStore`.

### load

```python
load(product_id: ProductId) -> StateSnapshot | None
```

Requirements:

- invalid `product_id` types raise `TypeError`
- a missing file returns `None`
- a valid document without the requested key returns `None`
- a stored snapshot is decoded into immutable Domain and Core objects
- the decoded product ID must equal both the requested ID and storage key
- the store reads the file on every call and retains no cache

### save

```python
save(snapshot: StateSnapshot) -> None
```

Requirements:

- invalid `snapshot` types raise `TypeError`
- a missing document creates schema version 1
- missing parent directories are created
- the unique storage key is `str(snapshot.product.id.value)`
- an existing key is replaced regardless of timestamp
- other raw snapshot entries are preserved
- the destination is replaced only after a complete temporary file is
  written, flushed and synchronized
- the temporary file is created in the destination directory with a unique
  name
- successful output is deterministic UTF-8 JSON using two-space indentation,
  sorted keys, `ensure_ascii=False` and one trailing newline
- no cache, system clock or environment variable is used

---

## Schema Version 1

Top-level fields:

```text
schema_version: integer 1
snapshots: object
```

Each snapshots key is a canonical UUID string. Its value contains:

```text
timestamp: timezone-aware ISO 8601 string
product: object
```

Product fields:

```text
id: UUID string
provider_id: UUID string
brand: string
name: string
current_price:
    amount: Decimal string
    currency: Currency value
original_price: null or Money object
discount_percent: Decimal string
url: string
image_url: null or string
created_at: timezone-aware ISO 8601 string
availability: boolean
```

All fields listed above are required, including nullable fields.

Unknown additional fields are ignored during decoding. Unsupported
`schema_version` values are rejected.

---

## Codec Behavior

Encoding must:

- preserve every current `Product` and `StateSnapshot` field
- encode UUIDs with `str(UUID)`
- encode `Decimal` values with `str(Decimal)`
- encode enum values with `.value`
- encode datetimes with `.isoformat()`
- never use `float` for money or percentages

Decoding must:

- validate required object, string, boolean and integer representations
- reconstruct `UUID`, `Decimal`, `Currency`, `Money`, `Percentage`,
  `ProductId`, `ProviderId`, `Product` and `StateSnapshot`
- rely on reconstructed Domain and snapshot objects for their invariants
- reject a snapshot when its map key differs from its product ID

Codec failures are internal value failures. The public store converts them to
`StateStoreError`.

---

## Error Handling

`StateStoreError` is raised for:

- file open, read, directory creation, temporary write, flush, fsync or
  replacement failures
- invalid UTF-8
- malformed JSON
- a non-object document root
- missing or invalid top-level fields
- unsupported schema version
- invalid stored snapshot or Product field representations
- Domain or snapshot invariant failures during reconstruction
- storage-key and product-ID mismatch

The original exception is preserved as `StateStoreError.__cause__`.

Invalid constructor, `load()` or `save()` argument types raise `TypeError` and
are never wrapped.

An unexpected programming exception is not silently converted unless it is a
document decoding or filesystem operation covered above.

---

## Atomic Failure Behavior

If an error occurs before `os.replace` completes:

- an existing destination file remains byte-for-byte unchanged
- the temporary file is removed when possible
- cleanup failure does not replace the original persistence failure

The first version provides no file locking, merge or multi-process conflict
handling.

---

## Dependency Rules

The implementation may import only:

- the public `core.domain` API
- the public `core.state` API
- Python standard library modules

No Core or Domain file may be modified.

The package must not import providers, rules, notifications, Applications,
Home Assistant, HTTP libraries or database libraries.

---

## Tests

Provide unit tests covering:

- `StateStore` Protocol compatibility
- constructor and method type validation
- construction without filesystem access
- missing file and unknown product behavior
- first save and parent directory creation
- load through a newly constructed store instance
- overwrite by product ID with last-write-wins semantics
- preservation of other snapshots
- exact round-trip of all Product fields, including original price and image
- in-stock and out-of-stock products
- exact Decimal values without float conversion
- timezone offsets for product and snapshot timestamps
- deterministic schema version 1 output and trailing newline
- every document structure and field type validation branch
- invalid UUID, Decimal, Currency and datetime values
- naive persisted timestamps
- storage-key mismatch
- malformed JSON and invalid UTF-8
- filesystem read, directory, temporary-write, fsync and replace failures
- preservation of the original destination on failed replacement
- temporary-file cleanup and cleanup failure behavior
- preservation of exception causes
- public export and public docstrings
- dependency boundaries and absence of clock, environment, provider, rule,
  notification, HTTP and database dependencies

Tests must use isolated temporary directories and must not access the network,
environment, database or global clock.

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0008 is followed exactly.
- `JsonStateStore` satisfies the existing `StateStore` Protocol.
- Core, Domain and existing public APIs are unchanged.
- A saved snapshot is available to a new store instance.
- Saving an existing product ID replaces only that product snapshot.
- All Product and snapshot values round-trip exactly.
- Money and percentage values never pass through `float`.
- Writes use adjacent temporary files and atomic replacement.
- Persistence failures raise `StateStoreError` with preserved causes.
- Invalid public argument types raise `TypeError`.
- Public API is exported through `__init__.py`.
- No TODOs, placeholders, pass statements, commented-out code or dead code
  remain.
- All tests pass with 100% statement and branch coverage.
