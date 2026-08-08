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

---

# v0.20.0 — Home Assistant Catalog Status

Goal:

Expose catalog health, product counts, qualifying discounts and last discovery
and refresh times without creating thousands of mandatory dashboard cards.

---
# v1.0.0

Stable public release.
