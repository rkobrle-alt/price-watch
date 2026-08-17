# STORY-031: Distinguish New Daily Discounts

## Objective

Implement ADR-0032 and release v0.31.0 so the daily Parkside email separates
newly qualifying products from discounts already present in the preceding
retained digest baseline.

## Scope

- extend the deterministic digest value and engine;
- add the provider-neutral baseline persistence Protocol;
- add SQLite schema 6 and its concrete baseline adapter;
- compose baseline comparison only in enabled Home Assistant catalog digests;
- update email, operator and release documentation.

Do not change discount qualification, reference-price policy, catalog
discovery, individual notification policy, digest calendar reservation,
promotion lookup, operational health semantics, CLI behavior or App options.

## Core Public API

Export `DailyDigestBaselineStore` from `core.notifications` with the exact
methods from ADR-0032. Returned product IDs are a unique tuple or `None`.

Append `new_product_ids: tuple[ProductId, ...] = ()` to
`DailyDiscountDigest`. It must be a unique tuple and every identifier must
belong to `products`.

Append
`previous_product_ids: tuple[ProductId, ...] | None = None` to
`DailyDiscountDigestEngine.generate`. Validate the complete tuple before
selection. `None` means no baseline and yields no new products; an empty tuple
is an available empty baseline and makes all qualifying products new.

Preserve existing qualification and ordering. Format only non-empty product
sections, use ADR-0032 headings exactly and restart numbering at one per
section. Preserve the existing header, promotion placement, product detail
shape and empty result text.

## Application Workflow

Append the keyword-only optional `baseline_store` dependency to
`DailyDigestWorkflow`. Validate its three callable methods structurally
without invoking them.

After a new date reservation and successful promotion lookup:

1. load latest snapshots;
2. load the latest preceding identifiers when a baseline store exists;
3. generate the digest with those identifiers;
4. stage the current digest product identifiers;
5. send the digest;
6. return the unchanged `DailyDigestResult` contract.

On generation, baseline or delivery failure, idempotently release the baseline
when configured, then release the date reservation and propagate according to
the existing compensation behavior. Promotion failure retains its current
earlier release and non-fatal result. `NOT_DUE` and `ALREADY_SENT` perform no
baseline access.

## SQLite

Upgrade the shared schema constant to 6. Fresh databases create:

```text
daily_digest_baselines(
    calendar_date TEXT PRIMARY KEY,
    product_ids TEXT NOT NULL
)
```

`product_ids` is a strict JSON document containing document version 1 and a
canonical UUID-sorted unique list. Valid schema versions 1 through 5 migrate
sequentially and transactionally to 6. The version-5 migration creates only
the new table and preserves every existing row exactly. Exact schema
validation includes the table and columns.

Create and export
`SqliteDailyDigestBaselineStore(path: Path, timeout_seconds: int = 5)`.
Construction performs no I/O. `previous_product_ids(date)` returns the newest
valid row with a date strictly before its argument or `None`. `stage` atomically
replaces that date's baseline. `release` is idempotent. Persisted malformed,
non-canonical, duplicate or incorrectly ordered values raise
`DailyDigestReservationError` with chaining. Invalid public types use
`TypeError`; duplicate input uses `ValueError`.

## Home Assistant Composition

Enabled catalog digest composition injects one
`SqliteDailyDigestBaselineStore` using the shared database path and timeout.
Disabled digest and explicit mode construct none. No option, permission,
sensor, notification title or service payload changes.

## Tests

Cover public exports, documentation, immutability, every new invariant,
baseline comparisons, products leaving and returning, exact section text,
workflow ordering and compensation, schema migration and rollback, strict
SQLite validation, Home Assistant composition and a restart-spanning
integration sequence. No test uses the network or is skipped. Statement and
branch coverage remains 100 percent.

## Acceptance Criteria

- the first digest without a prior baseline marks no item new;
- a product absent from the preceding baseline appears in the new section;
- an unchanged qualifying product appears in the other section;
- a product which leaves and later returns appears as new again;
- failed delivery does not become the comparison baseline;
- baseline membership survives App restart;
- one daily email, threshold and promotion behavior remain unchanged;
- schema migration preserves all existing data;
- existing callers may omit every new optional API argument;
- public APIs are documented and exported;
- all tests pass with 100 percent statement and branch coverage;
- no TODO, placeholder, pass statement, skipped test, commented code or dead
  code remains.

## Readiness Review

Specification is implementation-ready.
