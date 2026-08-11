# Application Flow

```text
CLI, scheduler or another application entry point
    |
    v
SynchronizationWorkflow
    |
    v
Provider.fetch
    |
    v
Current Products
    |
    v
ObservationHistory.history + PriceReferencePolicy (catalog alerts)
    |
    v
StateStore.load
    |
    v
RuleEngine.evaluate
    |
    v
NotificationEngine.generate
    |
    +--> no notification
    |
    +--> NotificationChannel.send
    |
    v
StateStore.save
```

---

The reusable orchestration belongs to `applications.synchronization` and
follows ADR-0009.

The first executable composition root is `applications.cli`. Its `sync`
command supplies the Lidl provider, JSON State Store, registered evaluators,
console channel, UTC clock and UUID generation according to ADR-0010.

Its `watch` command uses the same composition and delegates repeated execution
to `applications.scheduler.IntervalScheduler` according to ADR-0011. The first
cycle starts immediately. Later cycles start after a fixed delay following the
previous completed cycle, so synchronization cycles never overlap. The delay
side effect is supplied by `infrastructure.scheduler.SystemDelay`.

For configured execution, the CLI explicitly loads a versioned TOML document
through `infrastructure.configuration.toml.TomlConfigurationLoader`, validates
it through the pure `applications.configuration` parser and then enters the
same existing `sync` or `watch` composition. Relative state paths are resolved
against the TOML file directory. Configuration does not alter workflow stages.

The workflow depends only on public Core contracts and services. Applications
inject concrete providers, State Store implementations, notification channels
and identifier generation.

The reference State Store is
`infrastructure.persistence.memory.InMemoryStateStore`. Durable execution may
inject `infrastructure.persistence.json.JsonStateStore`, which preserves the
latest snapshot between process executions.

ADR-0017 adds `infrastructure.persistence.sqlite.SqliteStateStore` as a
catalog-scale alternative which preserves the same latest-snapshot contract
and also exposes ordered observation history. It is not selected by the
current CLI. ADR-0018 selects it together with `SqliteCatalogStore` for the
opt-in Home Assistant catalog mode.

ADR-0019 uses the same history in catalog mode to enrich each immutable
product with the approved reference price before evaluation. A provider
original price wins; otherwise the highest prior same-currency observation is
used. Explicit mode does not inject this policy.

Catalog monitoring adds an outer serial flow without replacing the existing
synchronization sequence:

```text
ProductCatalog.discover (on scheduled discovery cycles)
    |
    v
CatalogStore.record_discovery
    |
    v
CatalogRefreshStore.list_refresh_batch
    |
    v
SynchronizationWorkflow for selected URLs
    |
    v
CatalogRefreshStore.record_refresh_attempt
```

New or never-refreshed references have priority and the configured batch limit
also applies to first bootstrap. A sitemap failure is retained in the cycle
result while already known entries may still be refreshed. A propagated
synchronization failure leaves the batch unmarked for retry.

Snapshots are loaded and saved using `snapshot.product.id` as their unique
storage key.

For every product, all configured rules are evaluated against the stored
previous product and the current product. Applications invoke
`NotificationEngine.generate()` for every evaluation result. Only a generated
`Notification` is passed to the injected `NotificationChannel`.

Notification delivery occurs before the current snapshot is saved. A failed
delivery therefore does not advance comparison state. A retry after successful
delivery but failed persistence may repeat an unreserved notification.
Catalog price alerts reserve product, rule type, currency and current amount
in SQLite before delivery. A prior reservation suppresses generation; ordinary
delivery failures release a new reservation for retry. ADR-0019 documents the
hard-process-crash boundary where SQLite and Home Assistant cannot be atomic.

Provider-reported failures are collected without preventing later configured
providers from running. State Store, Rule Engine and notification failures
retain their subsystem exception types and stop the remaining cycle.

Core stages consume immutable input and produce immutable output. Side effects
remain behind injected Infrastructure boundaries.

The `applications.homeassistant` composition defined by ADR-0014 injects
`HomeAssistantNotificationChannel` in place of the Console channel without
changing synchronization ordering. It reads non-secret App options, uses
Supervisor-managed `/data/state.json`, starts immediately and delegates later
cycles to the same interval scheduler. The channel invokes
`notify.send_message`; Home Assistant remains responsible for SMTP delivery.

After the reusable workflow has completed, the Home Assistant composition
publishes read-only cycle and product state representations according to
ADR-0015. This post-workflow Infrastructure side effect cannot change rule,
notification or persistence results. A status-publication failure is reported
and counted but does not stop later scheduled monitoring cycles.

In catalog mode, ADR-0022 publishes dashboard-ready discounted-product, error
and latest-check representations from the already assembled catalog status.
These representations are published before the established aggregate health
entity, so a final `ok` update indicates that Home Assistant accepted the
complete overview for that cycle.

When enabled in catalog mode, ADR-0020 then invokes the reusable daily-digest
workflow with the same cycle timestamp. Before the configured Europe/Prague
wall-clock time it performs no persistence. At or after that time it reserves
the local date, reads the latest persisted snapshot for every product and
delivers one deterministic summary through the configured Home Assistant
notify entity. The durable date prevents a restart or later cycle from
repeating the same day's digest.

ADR-0024 inserts one read-only storage-diagnostics step after catalog status
publication and before the daily digest. A successful query publishes exact
observation counts, insertion-boundary timestamps and allocated bytes. An
approved catalog persistence failure attempts a warning publication without
reading the failed database and then retains the original fatal exception.

ADR-0026 optionally inserts a read-only retention-preview publication after
storage diagnostics and before the daily digest. It uses the injected cycle
timestamp and configured whole-day window, calls only the ADR-0025 planner and
adds no apply, backup, deletion or compaction path to Home Assistant.

ADR-0027 adds a separate one-shot Home Assistant command flow. It does not
enter or modify the scheduled sequence:

```text
hassio.addon_stdin explicit JSON action
    |
    v
strict command parsing
    |
    v
shared monitoring/maintenance lock
    |
    v
fresh retention plan
    |
    +--> stale expected count: no mutation
    |
    +--> zero removable count: no mutation
    |
    +--> matching positive count
            |
            +--> unique persistent backup
            |
            +--> transactional ADR-0025 apply
```

The App command listener and every monitoring cycle acquire the same lock, so
SQLite maintenance cannot overlap discovery, refresh, synchronization,
reservation or status work. The command always reuses the configured preview
window and never runs because of a restart or scheduled cycle.

ADR-0028 adds a deployment-only hand-off around, not inside, the monitoring
workflow:

```text
local App explicit export command
    |
    v
shared-lock SQLite/JSON snapshot + checksummed ZIP in /share
    |
    v
repository App explicit first-start import configuration
    |
    v
archive, option and state integrity validation
    |
    v
atomic install into the new App /data
    |
    v
ordinary composition and first monitoring cycle
```

The local App's source state is unchanged. A requested import must complete
before `_compose_homeassistant`; a failed import therefore cannot start an
empty-state monitoring cycle.

Manual retention is a separate operator flow and never enters the monitoring
sequence:

```text
CLI maintenance command
    |
    +--> plan: read and report protected/removable observations
    |
    +--> apply: acquire SQLite transaction
                 |
                 +--> write complete pre-deletion backup
                 |
                 +--> delete only planned observation rows
```

ADR-0025 preserves every recent observation, the latest inserted observation
per product and the earliest historical-high observation per product/currency.
It changes no catalog or reservation rows and performs no automatic vacuum.
