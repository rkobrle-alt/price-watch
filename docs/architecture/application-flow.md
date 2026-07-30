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

History Store

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