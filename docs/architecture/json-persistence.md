# JSON Persistence Architecture

## Purpose

JSON persistence stores the latest immutable product snapshot between process
executions. It is the first durable implementation of `core.state.StateStore`.

---

## Package

```text
infrastructure/persistence/json/
    __init__.py
    codec.py
    store.py
```

Responsibilities:

- `store.py` owns filesystem operations and `StateStoreError` translation
- `codec.py` owns the internal versioned JSON representation and Domain
  reconstruction
- `__init__.py` exports the public API

---

## Public API

The package exports:

- `JsonStateStore`

Constructor:

```python
JsonStateStore(path: Path)
```

Methods inherited structurally from `StateStore`:

```python
load(product_id: ProductId) -> StateSnapshot | None
save(snapshot: StateSnapshot) -> None
```

No codec object, schema constant or filesystem helper is public.

---

## Document Shape

```text
schema_version: 1
snapshots:
    product UUID:
        timestamp
        product:
            id
            provider_id
            brand
            name
            current_price:
                amount
                currency
            original_price
            discount_percent
            url
            image_url
            created_at
            availability
```

The map key must equal the decoded `product.id`.

All `Decimal` values are JSON strings. Datetimes are timezone-aware ISO 8601
strings. UUIDs and enum values use their public string forms.

---

## Load Flow

```text
ProductId
    |
    v
Read UTF-8 JSON file
    |
    +--> missing file: None
    |
    v
Validate document and schema version
    |
    +--> missing key: None
    |
    v
Decode Product and StateSnapshot
    |
    v
Immutable StateSnapshot
```

The store reads the file on every call and retains no cache.

---

## Save Flow

```text
StateSnapshot
    |
    v
Read existing document or create schema v1 document
    |
    v
Encode and replace snapshot by product ID
    |
    v
Write + flush + fsync adjacent temporary file
    |
    v
Atomic os.replace
```

Parent directories are created during `save()`, not construction.

---

## Error Boundary

Invalid public argument types raise `TypeError` directly.

Filesystem, JSON, schema and persisted-data failures are wrapped in
`StateStoreError` with their original cause preserved.

An error never produces a partial destination document.

---

## Dependency Rules

The package may import:

- `core.domain`
- `core.state`
- Python standard library modules

It must not import:

- Applications
- providers
- Rule Engine
- Notification Engine
- Home Assistant
- HTTP libraries
- database libraries

Core remains unaware of JSON and filesystem behavior.

---

## Operational Scope

The first implementation targets one process writing one file.

Atomic replacement protects readers from partial writes, but the store does
not provide cross-process locking, merging, history, backup rotation or schema
migration.
