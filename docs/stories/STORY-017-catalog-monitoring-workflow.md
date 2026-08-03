# STORY-017: Catalog Monitoring Workflow

## Objective

Implement bounded, durable Parkside catalog monitoring according to ADR-0018
and adopt it as an opt-in Home Assistant App mode. Reuse the existing Lidl
catalog, product provider and synchronization workflow without changing their
business behavior.

## Scope

Create:

```text
core/catalog/refresh_store.py
applications/catalog_monitoring/__init__.py
applications/catalog_monitoring/batch.py
applications/catalog_monitoring/result.py
applications/catalog_monitoring/workflow.py
```

Modify Core exports, SQLite schema and catalog store, Home Assistant option
parsing/composition/execution, App packaging documentation and corresponding
tests.

Do not modify Domain entities, Provider SDK, Lidl page or sitemap parsing,
Rule Engine evaluators, Notification Engine behavior, synchronization ordering,
CLI commands or JSON State Store behavior.

## Core Public API

`core.catalog` exports `CatalogRefreshStore` exactly as defined by ADR-0018.

Validation for both methods occurs before persistence:

- `provider_id` must be `ProviderId`
- `limit` must be a positive `int` and reject `bool`
- `references` must be a tuple containing only `ProductReference` values
- reference identities must be unique
- `attempted_at` must be a timezone-aware `datetime`
- every recorded identity must already exist in the catalog
- a timestamp earlier than an existing attempt raises `ValueError`

`record_refresh_attempt((), timestamp)` is valid and performs no changes.

## SQLite Behavior

Upgrade the shared SQLite schema constant to version 2.

Fresh databases create the version-2 schema directly. A valid version-1 Price
Watch database is migrated transactionally by adding nullable
`last_refresh_attempt_at` to `catalog_entries`, creating the refresh-order
index and setting `PRAGMA user_version = 2`.

Migration must preserve all catalog fields and observations exactly. Invalid
version-1 shapes are rejected before migration. A failed migration rolls back.
Version 0 foreign databases and versions other than 1 or 2 remain rejected.

`SqliteCatalogStore.list_refresh_batch()` returns:

1. never-attempted entries in catalog insertion order
2. attempted entries from oldest attempt to newest
3. catalog insertion order as the deterministic tie-breaker

Only entries for the requested provider are returned and at most `limit`
entries are decoded.

`record_refresh_attempt()` updates the complete tuple in one transaction.
Unknown references, duplicate identities or stale timestamps change nothing.
SQLite/schema/persisted-data failures raise `CatalogStoreError` with cause.

## Application Public API

`applications.catalog_monitoring` exports:

- `CatalogBatchSynchronizer`
- `CatalogMonitoringResult`
- `CatalogMonitoringWorkflow`

Their signatures and fields match ADR-0018 exactly.

All public objects have docstrings and explicit type hints. Result tuple
fields are validated and the result is immutable. Dependencies are validated
structurally without invoking them. `batch_size` is positive and rejects
`bool`.

`run()` validates rules, timestamp and `discover` before any dependency call.
The exact cycle behavior, discovery-error isolation, attempt recording and
empty-catalog behavior follow ADR-0018.

The workflow must not read time, generate UUIDs, sleep, access files, perform
HTTP, construct providers or contain rule logic.

## Home Assistant Configuration

Extend `HomeAssistantConfig` with an optional immutable catalog configuration
while preserving explicit-mode construction and behavior.

Catalog configuration contains:

- SQLite path fixed to `data_directory / "catalog.sqlite3"`
- positive `batch_size`
- positive `discovery_interval_cycles`
- positive timeout
- required interval
- existing optional exact price thresholds

App option rules:

- absent `catalog_enabled` means explicit mode
- `catalog_enabled` must be a boolean
- explicit mode requires non-empty `product_urls`
- catalog mode permits `product_urls` to be absent but rejects a supplied
  non-empty list as ambiguous
- `catalog_batch_size` and `catalog_discovery_interval_cycles` are allowed
  only in catalog mode and default to 25 and 288
- existing notify, interval, timeout, threshold and title validation remains
  unchanged
- unknown keys remain rejected

Invalid option documents raise `ConfigurationError`.

## Home Assistant Composition and Execution

Explicit mode must compose the existing `LidlParksideProvider`,
`JsonStateStore` and `SynchronizationWorkflow` unchanged.

Catalog mode composes:

- `LidlParksideCatalog` with `UrllibBinaryHttpClient`
- one shared `SqliteCatalogStore` and `SqliteStateStore` path
- `CatalogMonitoringWorkflow`
- a batch synchronizer which converts references to URLs, constructs the
  existing `LidlParksideProvider` and invokes a standard
  `SynchronizationWorkflow`
- the existing Rule Engine, Notification Engine, Home Assistant channel,
  status publisher, clock and notification ID factory

The first scheduled cycle sets `discover=True`. Later cycles set it when the
zero-based cycle number is divisible by `discovery_interval_cycles`. Process
restart resets the count and therefore discovers immediately.

Catalog cycle summaries include discovered, new, selected, product,
evaluation, notification, snapshot, provider-error and catalog-error counts.
Catalog errors are written to stderr and contribute to the existing
error-cycle outcome without stopping later cycles. Refreshed products are
published through the existing status publisher.

Known `CatalogStoreError` joins the existing fatal operational errors and
returns exit code 1. Existing explicit-mode output and exit behavior remains
backward compatible.

## App Packaging

Update `homeassistant/price_watch/config.yaml` so new installations default to
catalog mode with:

```yaml
catalog_enabled: true
catalog_batch_size: 25
catalog_discovery_interval_cycles: 288
```

The default interval remains 300 seconds. The default price threshold remains
unchanged until STORY-018 defines the durable 20-percent alert semantics.
Document SQLite persistence, bounded rotation and backward-compatible explicit
mode. Do not add permissions, ports, ingress, credentials or runtime
dependencies.

## Unit and Integration Tests

Cover:

- structural refresh Protocol compatibility and public exports
- every refresh API type/value validation branch
- new-first and oldest-first batch selection, provider filtering, limits and
  deterministic ties
- atomic attempt recording, unknown identities, stale timestamps and rollback
- fresh schema 2, exact version-1 migration, reopened stores and failed or
  incompatible migrations
- unchanged observation history after migration
- workflow ordering, optional discovery, same-cycle new priority, bounded
  bootstrap and empty catalog
- discovery-error isolation and propagation of persistence/synchronization
  failures
- no attempt mark after a propagated failure and marking after provider errors
- Home Assistant explicit-mode compatibility
- every catalog option default, validation and mutual-exclusion rule
- catalog composition and multi-cycle discovery cadence using fakes only
- status publication, summaries and exit codes in both modes
- package exports and dependency boundaries

Tests must not access the network. SQLite tests use temporary local databases.

## Acceptance Criteria

- ADR-0018 APIs and semantics are implemented exactly
- catalog batches remain bounded and rotate fairly across process restarts
- new references are eligible in the discovery cycle and prioritized
- discovery failures do not prevent refresh of retained entries
- the existing synchronization workflow remains the only rule/notification
  orchestration
- explicit Home Assistant and CLI behavior remains backward compatible
- catalog mode uses SQLite for both membership and observations
- every public API is exported through `__init__.py`
- all public objects have type hints and docstrings
- no TODOs, placeholders, `pass`, skipped tests, commented-out code or dead code
- the complete suite passes with 100 percent statement and branch coverage
