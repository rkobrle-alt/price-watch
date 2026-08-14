# Home Assistant Application Architecture

## Purpose

The Home Assistant App is an executable outer composition root for continuous
Price Watch monitoring and delivery through an existing Home Assistant notify
entity.

---

## Runtime Flow

```text
/data/options.json + SUPERVISOR_TOKEN
    |
    v
applications.homeassistant
    |
    +--> explicit mode: LidlParksideProvider + JsonStateStore(/data/state.json)
    +--> catalog mode: LidlParksideCatalog + bounded product batches
    |                  + reference-price enrichment
    |                  + shared SQLite history and alert reservations
    |                  + optional Europe/Prague daily discount digest
    |                  + optional individual product notifications
    +--> RuleEngine + NotificationEngine
    +--> HomeAssistantNotificationChannel
    +--> SynchronizationWorkflow
    +--> IntervalScheduler
    +--> HomeAssistantStatusPublisher
    +--> HomeAssistantCatalogStatusPublisher (catalog mode only)
    +--> HomeAssistantStorageStatusPublisher (catalog mode only)
    +--> optional HomeAssistantMaintenanceStatusPublisher (catalog mode only)
    +--> optional serialized retention command listener (catalog mode only)
```

The first cycle starts immediately. Later cycles use fixed delay and never
overlap.

ADR-0029 makes Supervisor `SIGTERM` a private process-lifecycle event at this
same executable boundary. It interrupts an active cycle or delay, reports the
completed-cycle counters when available and exits successfully. Interactive
`KeyboardInterrupt` and every established configuration or operational failure
retain their existing result codes. The handler is restored after the
programmatic `main()` call and introduces no cancellation contract into Core or
the reusable scheduler.

Existing option documents without `catalog_enabled` remain in explicit mode.
New packaged defaults enable catalog mode. The first catalog cycle discovers
the sitemap; later discovery follows the configured cycle cadence while every
cycle refreshes one persisted, fairly ordered batch.

An optional positive `retention_preview_days` catalog setting composes the
existing ADR-0025 planner and publishes `sensor.price_watch_maintenance` after
healthy storage diagnostics. Omitting it creates neither planner nor entity.
ADR-0027 additionally permits an explicit Supervisor-stdin command only when
that preview is configured. The command replans, compares the operator's
expected removable count and either rejects a stale plan, reports no changes
or invokes the existing backup-protected apply operation. It never runs during
startup merely because an option is present and never compacts SQLite.

The App manifest enables `stdin: true`. It adds no ingress, port, host mapping,
MQTT dependency or new API permission. A Home Assistant script may call
`hassio.addon_stdin`; the App accepts only the documented strict JSON object.
Scheduled cycles and commands share one lock and therefore never access the
catalog database concurrently.

After a workflow cycle completes, `HomeAssistantStatusPublisher` writes one
cycle status and one monetary sensor state for every successfully fetched
product. Product entity IDs derive from stable Product UUIDs. Status
publication is best-effort observability and cannot prevent later cycles.

Catalog mode additionally publishes one aggregate
`sensor.price_watch_catalog`. Its health, retained/observed/available and
qualifying-discount counts, configured threshold and durable last discovery and
refresh-attempt times summarize the complete catalog without requiring product
cards. Discount qualification reuses the deterministic Core digest engine.

ADR-0022 additionally projects the same validated catalog-cycle value into
dashboard-ready `sensor.price_watch_discounted_products`,
`sensor.price_watch_catalog_errors` and `sensor.price_watch_last_checked`
representations. The established aggregate health entity remains `ok` or
`degraded` and is published last.

ADR-0024 publishes `sensor.price_watch_storage` with read-only observation
counts, insertion-boundary timestamps and allocated SQLite bytes. A completed
read produces `ok`; an approved persistence failure attempts `warning` before
the original error stops the process. No diagnostic operation mutates data.
ADR-0025 adds exact reclaimable SQLite bytes to that representation after a
manual retention operation. The Home Assistant application never plans or
applies retention automatically. ADR-0027 confines apply to the explicit
standard-input action, creates a unique backup below
`/data/retention-backups` and republishes the preview after accepted commands.

---

## Boundaries

The JSON loader performs file I/O in Infrastructure. App-option conversion is
pure Application logic. Only the process adapter reads `SUPERVISOR_TOKEN`.
The fixed internal REST root is `http://supervisor/core/api`.

The same `UrllibHomeAssistantClient` instance supplies notification service
calls and state updates. State publication uses `POST /states/<entity_id>` and
does not create registry-backed integration entities.

The Core, Domain and reusable workflow are unaware of Home Assistant. The CLI
continues using console notification delivery.

The App publishes no token, credential or SMTP configuration in entity state.

---

## Persistence and Security

Explicit mode stores snapshots at `/data/state.json`. Catalog mode stores
catalog membership, refresh ordering and append-only observations at
`/data/catalog.sqlite3`. ADR-0019 also stores durable logical-price
reservations there. Catalog price alerts use a 20-percent packaged default,
historical-high fallback and available-only matching. Both paths are inside
Supervisor-managed persistent App storage. The App neither mounts Home
Assistant configuration nor requests host access.

ADR-0020 optionally composes one daily digest after a completed catalog cycle.
The digest reuses the configured price threshold and notify entity, reads the
latest SQLite state for every observed product and reserves one Europe/Prague
calendar date before delivery. It is unavailable in explicit mode.

ADR-0030 composes the Lidl global marketing-promotion source into that same
optional catalog digest. The source uses the existing text HTTP client and is
queried only for a newly eligible digest date. A temporary promotion failure
releases the date and returns a non-fatal retry outcome; ordinary catalog
monitoring continues. A missing banner is valid and sends the digest without a
promotion. No App option, sensor or persistent schema is added.

The Supervisor token is constructor input to the REST client only. It is not
part of `HomeAssistantConfig`, TOML, App options, logs or errors.

ADR-0023 separates catalog monitoring from individual email delivery. Existing
option documents retain individual price-drop and back-in-stock notifications.
The packaged default disables those individual rules and retains the daily
digest, so all current qualifying products are delivered in one email. This is
an Application composition choice; Core and the synchronization workflow do
not change.

---

## Distribution

The Home Assistant App manifest resides in `homeassistant/price_watch` and
references `ghcr.io/rkobrle-alt/price-watch`. A root Dockerfile packages the
existing source tree. Tag publication builds amd64 and aarch64 variants into
one OCI image manifest.

ADR-0028 makes the root `repository.yaml` and recursively discovered App
manifest the supported installation and update source. A repository install
has a different Supervisor identity and `/data` directory from the existing
`local_price_watch` installation; it is therefore never presented as an
in-place adoption.

The manifest maps Home Assistant `share` writable solely for an explicit
handoff through `/share/price-watch-migration`. The local App creates one
checksummed state bundle under the existing process lock. The repository App
validates and atomically imports that bundle before composing its first
monitoring cycle. Exported options are compared with current Supervisor
options but never replace `/data/options.json`. The unchanged stopped local
installation remains the immediate rollback path until acceptance succeeds.
Managed stop and restart acceptance additionally verifies that durable catalog
history and notification reservations remain present; it introduces no new
restore format beyond the ADR-0028 archive and Home Assistant backup.

ADR-0031 adds a separate durable operational representation without changing
the established `sensor.price_watch_status` or `sensor.price_watch_catalog`
contracts. Catalog mode persists provider-neutral health in the shared SQLite
database, publishes `sensor.price_watch_health` and
`sensor.price_watch_daily_digest`, and uses the configured notify entity for
one retryable sustained-incident message and one acknowledged-incident
recovery message. The fixed threshold is three failed catalog cycles.
