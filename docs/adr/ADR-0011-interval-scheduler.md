# ADR-0011: Interval Scheduler

## Status

Accepted

---

## Context

The CLI can execute one durable synchronization cycle, but an operator must
start every later cycle manually. Price and availability monitoring requires
the same composed workflow to run repeatedly without moving timing side
effects into Core or duplicating synchronization behavior in the CLI.

The first scheduler must remain small, deterministic under test and usable by
future application entry points.

---

## Decision

Interval orchestration belongs to:

```text
applications.scheduler
```

The package provides `IntervalScheduler`. It invokes one injected, argument-free
cycle immediately and then waits for an injected positive interval before each
later invocation. Scheduling uses fixed delay after a completed cycle. Cycles
never overlap.

Core contains only the `Delay` Protocol and `SchedulerError` contract in
`core.scheduler`. The protocol accepts `datetime.timedelta`; Core does not read
the clock, sleep or start threads.

The standard-library implementation belongs to
`infrastructure.scheduler.SystemDelay` and delegates to `time.sleep`.

---

## Public API

```python
class Delay(Protocol):
    def wait(self, duration: timedelta) -> None: ...
```

```python
class SchedulerError(RuntimeError): ...
```

```python
IntervalScheduler(
    cycle: Callable[[], None],
    delay: Delay,
)
```

```python
run(
    interval: timedelta,
    max_cycles: int | None = None,
) -> ScheduleResult
```

`ScheduleResult` is frozen and contains the number of successfully completed
cycles. `max_cycles` is an optional positive bound intended for finite runs,
automation and deterministic tests. When omitted, execution continues until a
cycle, delay or process interruption raises.

---

## CLI Integration

`applications.cli` adds a `watch` command. It accepts all `sync` configuration
and additionally requires `--interval-seconds`. Optional `--max-cycles` creates
a finite run. The command composes the same workflow once and calls it on every
scheduled cycle with a newly supplied cycle timestamp.

Provider-reported errors are displayed and recorded per cycle but do not stop
later scheduled cycles. A finite watch returns exit code `1` if any cycle
reported provider errors. State Store, Rule Engine, notification delivery and
scheduler failures stop the watch and return `1`.

Ctrl+C stops `watch`, reports the number of completed cycles and returns the
conventional process exit code `130`.

The existing `sync` command and its behavior remain unchanged. Its public
`run()` boundary gains an optional keyword-only `delay` dependency. The process
adapter always supplies `SystemDelay`; programmatic callers need it only for
`watch`.

---

## Validation and Failure Semantics

- invalid public argument types raise `TypeError`
- non-positive intervals and cycle limits raise `ValueError`
- cycle exceptions propagate from `IntervalScheduler` unchanged
- `KeyboardInterrupt` propagates to the application boundary
- `SystemDelay` translates only operational sleep failures into
  `SchedulerError`
- no retry, concurrency, catch-up or calendar scheduling is introduced

---

## Dependency Direction

```text
CLI
    +--> applications.scheduler
    +--> applications.synchronization
    +--> infrastructure.scheduler

applications.scheduler --> core.scheduler
infrastructure.scheduler --> core.scheduler
```

Core does not import Infrastructure or Applications. The reusable scheduler
does not import CLI or concrete Infrastructure.

---

## Alternatives Considered

### Put `time.sleep` in Core or Applications

Rejected because sleeping is a system side effect. The injected Protocol keeps
the scheduler deterministic and the concrete wait at the Infrastructure edge.

### Fixed-rate scheduling or overlapping cycles

Rejected for the first version because slow provider or persistence operations
would require concurrency and missed-deadline policy. Fixed delay provides
predictable serial execution.

### Rebuild the workflow on every interval

Rejected because configuration is stable for one process and the existing
workflow and store are reusable. Only the cycle timestamp is refreshed.

### Add a third-party scheduler

Rejected because a serial interval loop and standard-library sleep satisfy the
approved first milestone without a runtime dependency.

---

## Consequences

Advantages:

- practical repeated monitoring with durable comparison state
- no overlapping synchronization cycles
- deterministic scheduler unit tests
- one reusable scheduler independent of CLI and synchronization details
- existing one-shot command remains compatible

Costs:

- interval drift includes cycle duration
- no calendar expressions, daemonization, retries or distributed coordination
- process restart remains an external operational responsibility
