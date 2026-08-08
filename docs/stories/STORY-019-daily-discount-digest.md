# STORY-019: Daily Discount Digest

## Objective

Implement the optional Europe/Prague daily catalog discount summary according
to ADR-0020.

## Scope

Add deterministic Core digest APIs, reusable calendar orchestration, SQLite
latest-state querying and daily reservations, Home Assistant digest delivery,
schema version 4 and catalog-mode composition.

Do not change Domain entities, Provider SDK signatures, Rule Engine public
APIs, catalog discovery, refresh ordering, CLI behavior, JSON persistence or
explicit Home Assistant mode.

## Core Public API

`core.state` exports `LatestSnapshotReader` with the exact contract from
ADR-0020.

`core.notifications` exports:

- `DailyDiscountDigest`;
- `DailyDiscountDigestEngine`;
- `DailyDiscountDigestChannel`;
- `DailyDigestReservationStore`;
- `DailyDigestReservationError`.

The digest and every Application result/configuration value are frozen and
slotted. Public methods validate complete inputs before work. Datetimes must be
timezone-aware, dates must reject `datetime`, percentages remain Decimal based
and Core remains deterministic.

The engine must filter and order products exactly as ADR-0020 defines. Its
message must be deterministic and include a useful empty-state body.

## Application Public API

Create `applications.daily_digest` and export:

- `DailyDigestConfig`;
- `DailyDigestResult`;
- `DailyDigestStatus`;
- `DailyDigestWorkflow`.

`DailyDigestConfig` contains a local delivery `time` and minimum `Percentage`.
It rejects timezone-bearing times and sub-minute precision.

`DailyDigestStatus` has exactly `NOT_DUE = "not_due"`,
`ALREADY_SENT = "already_sent"` and `SENT = "sent"`.
`DailyDigestResult` contains `calendar_date: date`,
`status: DailyDigestStatus` and `product_count: int = 0`. The count is zero for
non-delivery statuses.

The workflow receives all collaborators, timezone and timestamps explicitly.
It follows ADR-0020 ordering and compensation exactly. Structural dependency
validation must not invoke collaborators.

## SQLite Persistence

Upgrade the shared schema constant to version 4.

Fresh databases create the daily reservation table. Valid versions 1, 2 and 3
migrate sequentially and transactionally without changing existing values.
Exact schema validation includes all four tables.

`SqliteStateStore.latest_snapshots()` returns the last inserted observation for
each product in canonical product-ID order and validates decoded storage keys.

`SqliteDailyDigestReservationStore` provides atomic reserve and idempotent
release. Invalid persisted ISO dates or timezone-aware timestamps raise
`DailyDigestReservationError` with chaining. SQLite failures retain the same
error boundary. Its public constructor is
`SqliteDailyDigestReservationStore(path: Path, timeout_seconds: int = 5)` and
it is exported through the SQLite package.

## Home Assistant Catalog Mode

Add strict options:

- `daily_digest_enabled`, default `false`;
- `daily_digest_time`, exact `HH:MM`, default `08:00` when enabled.

Reject digest options in explicit mode and reject `daily_digest_time` when the
feature is disabled. Enabling the digest requires a non-null
`price_drop_percentage`. Packaged defaults enable the digest at `08:00`.

Enabled catalog composition injects `ZoneInfo("Europe/Prague")`, the shared
`SqliteStateStore`, `SqliteDailyDigestReservationStore`, the deterministic
engine and a Home Assistant digest channel targeting the existing notify
entity.

Pin the official `tzdata` runtime package consistently in project metadata,
the development environment and the Home Assistant image.

`infrastructure.notifications.homeassistant` exports
`HomeAssistantDailyDiscountDigestChannel(client, entity_id,
title="Price Watch Daily Digest")`. It implements the Core digest channel and
maps operational client failures to `NotificationError`.

Execute the digest after each completed catalog synchronization/status phase
using that cycle's timestamp. When enabled, include `digest_status` and
`digest_products` in catalog output. Disabled catalog and explicit output
remain unchanged.

Map digest reservation failures like persistence failures and digest channel
failures through the existing notification error boundary.

## Tests

Cover:

- digest value, Protocol and public export validation;
- every selection, threshold, empty-state, ordering and formatting branch;
- before-time, exact-time, after-time, timezone conversion, already-sent,
  successful delivery and release-on-failure paths;
- DST dates through real `Europe/Prague` timezone data;
- configuration defaults, strict parsing and mode restrictions;
- fresh schema 4 and exact sequential migrations from versions 1, 2 and 3;
- latest snapshot selection, ordering and adapter failures;
- atomic daily reserve, persistence across reopen, idempotent release and
  malformed persisted data;
- catalog-only Home Assistant composition, delivery payload and cycle summary;
- an integration sequence across cycles and process recomposition proving one
  digest per local date.

Tests use fakes and temporary SQLite databases and never access the network.

## Acceptance Criteria

- disabled configuration performs no digest persistence or delivery;
- a cycle before 08:00 Europe/Prague does not send;
- the first cycle at or after 08:00 sends one digest for the local date;
- later cycles and App recomposition on the same date do not resend;
- the next local date can send once;
- only available products with an approved reference and discount at or above
  the configured percentage appear;
- an empty qualifying set still sends one explicit empty summary;
- reported generation or delivery failure permits retry on the next cycle;
- migrations preserve all pre-existing rows exactly;
- CLI and explicit Home Assistant behavior remain backward compatible;
- every public API is exported through `__init__.py` and documented;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- the complete suite has 100 percent statement and branch coverage.
