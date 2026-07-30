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

Candidate:

- Alza.cz

---

# v0.7.0 — JSON Persistence

Goal:

Persist product state between executions.

Initial implementation:

- JSON

---

# v0.8.0 — Application Workflow

Goal:

Compose one complete synchronization cycle according to ADR-0005.

The workflow connects:

- Provider
- State Store
- Rule Engine
- Notification Engine

---

# v0.9.0 — CLI

Goal:

Allow the whole platform to be executed from the command line.

Commands:

- sync
- evaluate
- version

---

# v0.10.0 — Scheduler

Goal:

Execute synchronization cycles.

Initially:

- Manual execution
- Interval scheduling

---

# v1.0.0

Stable public release.