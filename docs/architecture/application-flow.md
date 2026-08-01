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

Snapshots are loaded and saved using `snapshot.product.id` as their unique
storage key.

For every product, all configured rules are evaluated against the stored
previous product and the current product. Applications invoke
`NotificationEngine.generate()` for every evaluation result. Only a generated
`Notification` is passed to the injected `NotificationChannel`.

Notification delivery occurs before the current snapshot is saved. A failed
delivery therefore does not advance comparison state. A retry after successful
delivery but failed persistence may repeat the logical notification.

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
