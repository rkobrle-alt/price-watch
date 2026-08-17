# ADR-0032: New Discounts in the Daily Digest

## Status

Accepted

## Context

The daily Parkside email lists every currently qualifying discount in one
deterministic order. Once the catalog grows, the operator cannot quickly tell
which products were absent from the preceding successfully accepted daily
digest.

"New" must describe a change in the delivered discount set, not merely recent
catalog discovery. A previously known product can become newly discounted,
and a product which leaves the qualifying set and later returns must be new
again. The comparison must survive App restarts and must not introduce time,
SQLite or Home Assistant dependencies into Core.

## Decision

A product is new in a daily digest when its `ProductId` is present in the
current qualifying set and absent from the most recent earlier retained digest
baseline. An absent baseline establishes the current set without marking any
product as new. An empty retained baseline is valid and makes every current
qualifying product new.

The deterministic digest engine receives an optional tuple of prior product
identifiers. It computes the new subset after applying the existing
qualification and ordering rules. The immutable digest retains the new product
identifiers and validates that they are unique members of `products`.

Non-empty email content separates products into these sections, omitting an
empty section:

```text
🆕 NOVĚ VE SLEVĚ (<count>)

1. <product>

OSTATNÍ AKTUÁLNÍ SLEVY (<count>)

1. <product>
```

Each section preserves the established descending-discount, name and UUID
order and restarts numbering at one. The promotion and aggregate header remain
before both sections. Empty digests retain the established empty message.

## Durable Baseline

Core adds a `DailyDigestBaselineStore` Protocol with:

```python
previous_product_ids(
    calendar_date: date,
) -> tuple[ProductId, ...] | None

stage(
    calendar_date: date,
    product_ids: tuple[ProductId, ...],
) -> None

release(calendar_date: date) -> None
```

The Application reserves the date, retrieves optional promotion and current
snapshots, loads the preceding baseline, generates the digest, stages the
current qualifying identifiers and then delivers the message. Any reported
generation, staging or delivery failure releases both the staged baseline and
the daily reservation before propagating, except for the established
non-fatal promotion outcome which occurs before baseline work.

Staging occurs before external delivery. A hard process stop after staging and
before Home Assistant acceptance retains the same accepted reservation-before-
delivery suppression boundary documented by ADR-0020; it does not create a
second independent crash window.

SQLite schema version 6 adds `daily_digest_baselines` with a calendar-date
primary key and a strict versioned JSON tuple of canonical product UUIDs.
Schema 5 migrates transactionally without modifying existing tables or rows.
No row means no baseline. The concrete
`SqliteDailyDigestBaselineStore` implements the Core Protocol and returns the
latest row strictly before the requested date. Values are stored in canonical
UUID order, independently from presentation order.

The reusable workflow accepts an optional baseline store for backward
constructor compatibility. Home Assistant catalog composition always injects
the SQLite implementation when the digest is enabled. Callers which omit it
establish no cross-run comparison and produce no new-product markers.

## Public API

`core.notifications` additionally exports `DailyDigestBaselineStore`.
`DailyDiscountDigest` gains the backward-compatible final field:

```python
new_product_ids: tuple[ProductId, ...] = ()
```

`DailyDiscountDigestEngine.generate(...)` gains the backward-compatible final
argument:

```python
previous_product_ids: tuple[ProductId, ...] | None = None
```

`DailyDigestWorkflow(...)` gains the keyword-only optional dependency:

```python
baseline_store: DailyDigestBaselineStore | None = None
```

`infrastructure.persistence.sqlite` additionally exports
`SqliteDailyDigestBaselineStore`. Baseline persistence failures use the
existing `DailyDigestReservationError` digest-persistence boundary.

Invalid public argument types raise `TypeError`. Duplicate identifiers or
invalid membership invariants raise `ValueError`.

## Dependency Direction

```text
applications.daily_digest --> core.notifications
applications.homeassistant --> infrastructure.persistence.sqlite
infrastructure.persistence.sqlite --> core.notifications + core.domain IDs
core.notifications --> core.domain
```

Core remains deterministic and independent of SQLite, Home Assistant and the
system clock. Infrastructure imports no Application package.

## Alternatives Considered

### Use catalog `first_seen_at`

Rejected because it misses an existing product which becomes discounted later
and incorrectly treats catalog novelty as discount novelty.

### Compare with yesterday's observations

Rejected because observation history does not identify what the operator was
shown, and a missed delivery day makes the result ambiguous.

### Mark every item in the first upgraded digest as new

Rejected because migration has no truthful preceding delivered membership and
would create a noisy one-time result. The first digest establishes a baseline.

### Store comparison state in Home Assistant

Rejected because reusable digest behavior would become deployment-specific
and restart semantics would depend on external entity state.

## Consequences

The daily email makes newly qualifying and returning discounts immediately
visible while retaining one-message-per-day behavior. One small SQLite row is
added per delivered digest date. The first eligible digest after deployment
is intentionally a baseline; novelty appears from the following successful
comparison onward.
