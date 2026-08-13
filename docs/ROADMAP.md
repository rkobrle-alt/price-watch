# Price Watch Roadmap

## Vision

Build a modular platform for monitoring products, detecting changes and delivering notifications.

The Core remains independent of providers, storage, notification channels and applications.

---

# v0.4.0 — State Store

Goal:

Introduce the abstraction responsible for loading and storing the previous state of products.

Deliverables:

- `core.state.StateStore` Protocol
- `core.state.StateSnapshot`
- `core.state.StateStoreError`
- `infrastructure.persistence.memory.InMemoryStateStore`
- Unit tests

---

# v0.5.0 — Notification Engine

Goal:

Generate notifications from evaluation results.

Initial channel:

- Console

Architecture prepared for:

- Email
- Telegram
- Discord
- Home Assistant

---

# v0.6.0 — First Provider

Goal:

Implement the first real provider.

Provider:

- Lidl Czech Republic
- Parkside tools
- Explicit product URL monitoring

---

# v0.7.0 — JSON Persistence

Goal:

Persist product state between executions.

Initial implementation:

- versioned JSON document
- exact Domain snapshot round-trip
- atomic file replacement

---

# v0.8.0 — Application Workflow

Goal:

Compose one complete synchronization cycle according to ADR-0005.

The workflow connects:

- multiple injected Providers with failure isolation
- previous-state loading and current-state persistence
- Rule Engine evaluation
- Notification Engine generation and injected delivery
- deterministic cycle timestamps and notification identifiers

---

# v0.9.0 — CLI

Goal:

Allow the whole platform to be executed from the command line.

Commands:

- `sync` for one durable Lidl Parkside synchronization cycle
- `version` for release identification

A standalone `evaluate` command is deferred until an external Product and Rule
input contract is approved. Practical evaluation is performed by `sync`.
---

# v0.10.0 — Scheduler

Goal:

Execute synchronization cycles repeatedly at an explicit interval.

Deliverables:

- reusable serial `IntervalScheduler`
- Core delay abstraction and Infrastructure system-delay adapter
- CLI `watch` command
- immediate first cycle and fixed delay between completed cycles
- optional finite cycle limit and graceful Ctrl+C handling

---

# v0.11.0 — Application Configuration

Goal:

Start the existing synchronization commands from one repeatable, explicit
configuration file.

Deliverables:

- versioned strict TOML schema
- pure immutable Application configuration
- Infrastructure TOML loader
- `sync --config` and `watch --config`
- exact Decimal thresholds and config-relative state paths
- no environment discovery or secret storage

---

# v0.12.0 — Home Assistant Notifications

Goal:

Delegate actionable Price Watch notifications to an existing Home Assistant
notify entity.

Deliverables:

- deterministic rich notification messages
- Home Assistant service client contract and standard-library REST adapter
- `HomeAssistantNotificationChannel`
- reuse of Home Assistant SMTP without duplicated credentials
- no App packaging or Supervisor-token discovery yet

---

# v0.13.0 — Home Assistant Application

Goal:

Run the complete Price Watch workflow continuously as a Home Assistant App.

Deliverables:

- Supervisor-managed App options and persistent `/data` state
- safe `SUPERVISOR_TOKEN` injection at the process boundary
- `notify.gmail_parkside_kobrle_fomei_com` as the default configurable delivery entity
- existing synchronization workflow and serial scheduler composition
- minimal-permission amd64/aarch64 App packaging
- GHCR image publishing workflow

---

# v0.13.1 — SMTP Entity Correction

Goal:

Use the verified SMTP-backed Home Assistant notify entity as the deployment default.

Deliverables:

- corrected App default and operator documentation
- unchanged configurable notify-entity boundary
- regression coverage for the packaged default

---

# v0.14.0 — Home Assistant Status Entities

Goal:

Make completed monitoring cycles and current product prices visible in Home
Assistant without adding a separate UI or integration runtime.

Deliverables:

- cycle health state at `sensor.price_watch_status`
- deterministic monetary product sensor states
- existing Core API proxy and permission reuse
- non-fatal observability failure handling
- no Core, Domain or workflow contract changes

---

# v0.15.0 — Parkside Catalog Discovery

Goal:

Discover Parkside and Parkside Performance candidates from the
robots-advertised Lidl Czech Republic product sitemap.

Deliverables:

- provider-neutral catalog contract and immutable references
- bounded binary HTTP adapter
- sitemap-only Lidl catalog implementation
- no search, pagination, product-page retrieval or persistence

---

# v0.16.0 — Catalog and Observation History

Goal:

Persist catalog membership and exact price and availability observations at
practical catalog scale.

Deliverables:

- provider-neutral catalog-entry and catalog-store Core contracts
- read-only observation-history Core contract
- shared lossless snapshot codec for durable stores
- versioned `SqliteCatalogStore` and `SqliteStateStore`
- atomic catalog batches and exact append-only observation history
- compatibility with the existing latest-snapshot State Store contract
- explicit schema initialization and no automatic data deletion

---

# v0.17.0 — Catalog Monitoring Workflow

Goal:

Refresh new products immediately and existing products in bounded, serial
batches without overlapping cycles or prohibited crawling.

Deliverables:

- durable never-refreshed-first and oldest-attempt-first batch ordering
- transactional SQLite schema 1 to 2 migration
- reusable `applications.catalog_monitoring` orchestration
- sitemap-discovery failure isolation with retained-catalog refresh
- opt-in Home Assistant catalog mode using shared SQLite persistence
- backward-compatible explicit URL mode and unchanged CLI

---

# v0.18.0 — Twenty-Percent Alerts

Goal:

Send one notification when a current price is at most 80 percent of its
approved reference price, with durable deduplication.

Deliverables:

- reliable original-price then historical-high reference selection
- available-only catalog price alerts with a 20-percent packaged default
- structured price-alert identity and durable SQLite reservations
- transactional SQLite schema 2 to 3 migration
- suppression count in catalog cycle output
- unchanged explicit URL and CLI behavior

---

# v0.19.0 — Daily Discount Digest

Goal:

Optionally send one Europe/Prague calendar-based daily summary of currently
available Parkside products discounted by at least 20 percent.

Deliverables:

- deterministic digest selection and channel-neutral content
- configurable `HH:MM` delivery time with Europe/Prague calendar semantics
- restart-safe one-per-local-date SQLite reservation
- transactional SQLite schema 3 to 4 migration
- Home Assistant notify delivery in catalog mode
- disabled-by-default backward-compatible option parsing

---

# v0.20.0 — Home Assistant Catalog Status

Goal:

Expose catalog health, product counts, qualifying discounts and last discovery
and refresh times without creating thousands of mandatory dashboard cards.

Deliverables:

- provider-neutral durable catalog statistics contract
- one aggregate `sensor.price_watch_catalog` state representation
- retained, observed, available and qualifying-discount counts
- restart-safe last discovery and refresh-attempt timestamps
- healthy/degraded current-cycle status
- unchanged explicit-URL mode and existing status entities

---
# v0.21.0 — Home Assistant Operational Overview

Goal:

Make the most useful catalog outcome and current operational diagnostics
visible directly as native Home Assistant dashboard states.

Deliverables:

- numeric currently discounted Parkside product state
- numeric current-cycle catalog error state
- latest completed catalog-check timestamp state
- delivered and suppressed individual-alert diagnostics
- backward-compatible `sensor.price_watch_catalog` health contract
- unchanged Core, persistence schema, App options and explicit mode

---

# v0.22.0 — Digest-Only Notifications

Goal:

Deliver all current qualifying Parkside discounts and links in one daily email
without sending a separate email for every product.

Deliverables:

- backward-compatible catalog-only individual-notification option
- packaged digest-only default for new installations
- unchanged daily reservation and Europe/Prague scheduling
- continued discovery, history and dashboard publication
- unchanged Core, persistence, CLI and explicit mode

---

# v0.23.0 — Observation Storage Diagnostics

Goal:

Measure long-term SQLite observation growth and expose storage health without
deleting or rewriting user history.

Deliverables:

- provider-neutral observation statistics contract
- read-only SQLite counts, insertion-boundary timestamps and allocated bytes
- `sensor.price_watch_storage` healthy and warning representations
- original persistence-error propagation after best-effort warning publication
- unchanged schema version 4 and indefinite retention

---

# v0.24.0 — Manual Observation Retention

Goal:

Allow an operator to preview and explicitly reduce detailed observation
history without changing the latest product state or historical-high discount
reference.

Deliverables:

- immutable provider-neutral retention plan and result contracts
- SQLite retention adapter preserving recent, latest and historical-high rows
- mandatory complete backup before explicit deletion
- plan-by-default CLI `maintenance` command
- reclaimable-byte Home Assistant storage diagnostics
- unchanged schema version 4 and no scheduled retention or automatic vacuum

---

# v0.25.0 — Home Assistant Retention Preview

Goal:

Show the impact of an explicitly configured retention window in Home
Assistant without making destructive maintenance available to the App.

Deliverables:

- optional catalog-only retention preview window
- read-only `sensor.price_watch_maintenance` representation
- exact cutoff and total, removable, retained and protected counts
- unchanged CLI-only apply and mandatory backup boundary
- no deletion, backup, compaction or schema migration in Home Assistant

---

# v0.26.0 — Home Assistant Retention Command

Goal:

Apply a freshly revalidated retention preview through an explicit Home
Assistant action without scheduling deletion or opening another network
surface.

Deliverables:

- strict one-shot JSON command through Supervisor-managed App stdin
- stale-plan count confirmation before mutation
- serialized monitoring and maintenance database access
- unique complete backup in persistent App storage before deletion
- refreshed maintenance representation after the command
- unchanged schema version 4 and no automatic vacuum

---

# v0.27.0 — Managed Home Assistant Distribution

Goal:

Install and update Price Watch from its GitHub Home Assistant App repository
without losing the state of the existing local installation.

Deliverables:

- discoverable repository installation and normal managed updates
- explicit checksummed state export to the Home Assistant shared directory
- pre-cycle import into the repository App's independent `/data`
- preservation of catalog history and notification reservations
- verified configuration hand-off and unchanged sensor entity IDs
- retained local installation and Home Assistant backup for rollback

---

# v0.28.0 — Home Assistant Production Readiness

Goal:

Make a Supervisor-requested App stop a prompt, successful lifecycle event and
verify that managed stop and restart preserve durable monitoring state.

Deliverables:

- process-local `SIGTERM` handling at the Home Assistant executable boundary
- successful exit status for Supervisor-requested shutdown
- unchanged interactive-interrupt and operational-failure exit semantics
- documented managed-App stop, restart and state-preservation acceptance check
- unchanged Core, persistence formats, schema version 4 and public APIs

---

# v0.29.0 — Daily Lidl Promotion

Goal:

Include the current global Lidl Czech Republic marketing message and its
actionable link in the existing daily Parkside discount email.

Deliverables:

- provider-neutral immutable daily-promotion contract
- server-rendered Lidl marketing-banner adapter
- deterministic promotion block in empty and non-empty daily digests
- non-fatal reservation-releasing retry on temporary promotion lookup failure
- unchanged product, Provider SDK, Rule Engine, schema and App options

---

# v1.0.0

Stable public release.
