# STORY-010: Interval Scheduler

## Goal

Implement repeated, non-overlapping synchronization according to ADR-0011 and
expose it through the CLI as `watch`.

---

## Package Structure

Create:

```text
core/scheduler/
    __init__.py
    delay.py
    exceptions.py

applications/scheduler/
    __init__.py
    interval.py
    result.py

infrastructure/scheduler/
    __init__.py
    system.py

tests/unit/scheduler/
    __init__.py
    test_core_contract.py
    test_interval_scheduler.py
    test_public_api.py
    test_system_delay.py
```

Extend the existing CLI modules and tests for the `watch` command. Update
project metadata to version `0.10.0` only in the release commit.

---

## Public API

Export through `core.scheduler`:

- `Delay`
- `SchedulerError`

Export through `applications.scheduler`:

- `IntervalScheduler`
- `ScheduleResult`

Export through `infrastructure.scheduler`:

- `SystemDelay`

`Delay` signature:

```python
wait(duration: timedelta) -> None
```

`IntervalScheduler` signatures:

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

`ScheduleResult` is a frozen, slotted dataclass with:

```python
cycles_completed: int
```

Extend `applications.cli.run()` with the backward-compatible keyword-only
parameter:

```python
delay: Delay | None = None
```

Every public object has explicit typing and documentation.

---

## Scheduler Behavior

- validate the cycle callable and structural `Delay` dependency at construction
- validate `interval` as a strictly positive `timedelta`
- reject `bool` and non-`int` cycle limits with `TypeError`
- validate `max_cycles`, when present, as strictly positive
- invoke the first cycle immediately
- wait exactly once between successfully completed cycles
- never wait after the final bounded cycle
- execute cycles serially without threads or overlap
- return the exact completed count after a bounded run
- let cycle, delay and interruption exceptions propagate unchanged
- for an unbounded run, continue until an exception or interruption occurs

`ScheduleResult` rejects an invalid type or negative completed count.

---

## System Delay

`SystemDelay.wait()` validates the same positive `timedelta` contract and calls
the injected standard-library-compatible sleep callable with
`duration.total_seconds()`.

Its constructor accepts the sleep callable for deterministic unit tests and
defaults to `time.sleep`. An `OSError` or `OverflowError` from that callable is
translated to `SchedulerError` with exception chaining. `KeyboardInterrupt`
and unexpected failures propagate unchanged.

---

## CLI Command

```text
price-watch watch \
    --state-file PATH \
    --url HTTPS_LIDL_PRODUCT_URL \
    [--url HTTPS_LIDL_PRODUCT_URL ...] \
    --interval-seconds POSITIVE_INTEGER \
    [--max-cycles POSITIVE_INTEGER] \
    [--timeout-seconds POSITIVE_INTEGER] \
    [--price-drop-percentage DECIMAL] \
    [--price-drop-amount DECIMAL]
```

`watch` reuses all `sync` parsing and composition rules. Arguments are stored
in an immutable `WatchArguments` containing validated `SyncArguments`, a
positive `timedelta` interval and optional positive cycle limit.

The CLI composes one workflow and one `IntervalScheduler`. Every scheduled
callback obtains a fresh timezone-aware timestamp from the injected clock and
runs that same workflow and built-in rule tuple.

Every completed cycle writes the existing exact `sync complete:` summary and
provider-error diagnostics. Provider errors do not stop scheduling. After a
finite run, stdout receives:

```text
watch complete: cycles=C provider_error_cycles=E\n
```

The finite command returns `1` when `E` is non-zero, otherwise `0`.

On `KeyboardInterrupt`, stdout receives:

```text
watch stopped: cycles=C provider_error_cycles=E\n
```

and the command returns `130`. A cycle counts as completed only after the
synchronization workflow returned and its cycle diagnostics were written.

A missing injected delay for programmatic `watch` raises `TypeError`. `main()`
supplies `SystemDelay` and retains all other real process dependencies.

Known `StateStoreError`, `RuleError`, `NotificationError` and `SchedulerError`
values write `error: MESSAGE\n` to stderr and return `1`. Parser and composition
errors retain exit code `2`. Unexpected failures propagate.

The existing `sync` and `version` output and exit semantics do not change.

---

## Dependency Rules

- Core contains scheduler contracts only and performs no sleep or other I/O.
- `applications.scheduler` imports only standard-library and Core contracts.
- `infrastructure.scheduler` implements the Core delay boundary.
- CLI is the only package that composes scheduler, workflow and concrete delay.
- Scheduler packages contain no provider, rule, persistence or notification
  logic.
- Existing Domain, Provider SDK, Rule Engine, State Store, Notification Engine
  and Synchronization Workflow public APIs are unchanged.

---

## Tests

Unit tests must cover:

- Protocol conformance and public exports
- all public validation branches
- immutable result validation
- immediate first execution
- exact wait ordering and duration
- bounded and unbounded execution paths
- cycle and delay exception propagation
- system sleep conversion and operational error translation
- `watch` parser defaults and validation
- immutable `WatchArguments`
- reuse of exact sync composition
- fresh cycle timestamps
- finite success and provider-error exit codes
- Ctrl+C before, between and during cycles
- known scheduler failure mapping and unexpected failure propagation
- unchanged `sync` and `version` behavior
- dependency direction and absence of business logic

Tests use no real sleep, network, environment or global streams.

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0011 and every earlier accepted ADR are followed.
- `price-watch watch` repeatedly invokes one composed workflow.
- the first cycle starts immediately and later cycles use fixed delay.
- cycles never overlap.
- persisted JSON state is reused between scheduled cycles.
- provider partial failures do not stop later cycles.
- Ctrl+C exits cleanly with code `130`.
- Core remains deterministic and Infrastructure owns real sleeping.
- `sync` stays backward compatible.
- every public API is exported through `__init__.py`.
- no TODOs, placeholders, pass statements, commented code or dead code remain.
- all tests pass with 100% statement and branch coverage.
