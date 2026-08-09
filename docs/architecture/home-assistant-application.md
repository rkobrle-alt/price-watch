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
```

The first cycle starts immediately. Later cycles use fixed delay and never
overlap.

Existing option documents without `catalog_enabled` remain in explicit mode.
New packaged defaults enable catalog mode. The first catalog cycle discovers
the sitemap; later discovery follows the configured cycle cadence while every
cycle refreshes one persisted, fairly ordered batch.

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
