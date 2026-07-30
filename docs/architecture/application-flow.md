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

Delivery
```

---

The workflow depends on the `StateStore` abstraction from `core.state`.

Applications inject a concrete implementation from Infrastructure.

The reference implementation is
`infrastructure.persistence.memory.InMemoryStateStore`.

Snapshots are loaded and saved using `snapshot.product.id` as their unique
storage key.

---

Every stage consumes immutable input.

Every stage produces immutable output.

No stage skips another.

The flow is always:

Retrieve

↓

Compare

↓

Evaluate

↓

Notify
