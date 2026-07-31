# Application Flow

```
Scheduler

    │

    ▼

Provider

    │

    ▼

Current Products

    │

    ▼

State Store

    │

    ▼

Rule Engine

    │

    ▼

Evaluation Results

    │

    ▼

Notification Engine

    │

    ▼

Notification Channel

    │

    ▼

Delivery
```

---

The workflow depends on the `StateStore` abstraction from `core.state`.

Applications inject a concrete implementation from Infrastructure.

The reference implementation is
`infrastructure.persistence.memory.InMemoryStateStore`.

Durable execution may inject
`infrastructure.persistence.json.JsonStateStore`. It preserves the latest
snapshot between process executions without changing the Core workflow.

Snapshots are loaded and saved using `snapshot.product.id` as their unique
storage key.

Applications invoke `NotificationEngine.generate()` for every evaluation
result. Only a generated `Notification` is passed to the injected
`NotificationChannel`.

Concrete notification channels belong to Infrastructure. Core performs no
delivery side effects.

---

Core stages consume immutable input and produce immutable output.

A `NotificationChannel` consumes an immutable `Notification` and performs a
delivery side effect in Infrastructure.

Every synchronization cycle follows:

Retrieve

↓

Compare

↓

Evaluate

↓

Generate Notification

↓ when a Notification exists

Deliver
