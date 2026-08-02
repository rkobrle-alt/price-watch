# Price Watch Roadmap

## Vision

Build a modular platform for monitoring products, detecting changes and delivering notifications.

The Core remains independent of providers, storage, notification channels and applications.

---

# v0.4.0 â€” State Store

Goal:

Introduce the abstraction responsible for loading and storing the previous state of products.

Deliverables:

- `core.state.StateStore` Protocol
- `core.state.StateSnapshot`
- `core.state.StateStoreError`
- `infrastructure.persistence.memory.InMemoryStateStore`
- Unit tests

---

# v0.5.0 â€” Notification Engine

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

# v0.6.0 â€” First Provider

Goal:

Implement the first real provider.

Provider:

- Lidl Czech Republic
- Parkside tools
- Explicit product URL monitoring

---

# v0.7.0 â€” JSON Persistence

Goal:

Persist product state between executions.

Initial implementation:

- versioned JSON document
- exact Domain snapshot round-trip
- atomic file replacement

---

# v0.8.0 â€” Application Workflow

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

# v0.10.0 â€” Scheduler

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

# v1.0.0

Stable public release.
