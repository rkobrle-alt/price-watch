# ADR-0010: Command-Line Interface

## Status

Accepted

---

## Context

The platform now has a complete reusable synchronization workflow but no
user-facing entry point. A local operator must be able to configure Lidl
Parkside product URLs, durable state and optional price thresholds and then
execute one cycle without writing Python composition code.

The CLI is an outer Application boundary. It may read process arguments,
standard streams, the system clock and UUID randomness, but must not contain
provider parsing, persistence, rule evaluation or notification business logic.

---

## Decision

The first CLI belongs to:

```text
applications.cli
```

It is available through both:

```text
price-watch
python -m applications.cli
```

The CLI composes existing public services and Infrastructure implementations.
It does not reproduce `SynchronizationWorkflow` behavior.

---

## Commands

### sync

`sync` performs one synchronization cycle using:

- `LidlParksideProvider`
- `UrllibTextHttpClient`
- `JsonStateStore`
- `PriceDropEvaluator`
- `BackInStockEvaluator`
- `NotificationEngine`
- `ConsoleNotificationChannel`
- `SynchronizationWorkflow`

Required arguments:

```text
--url HTTPS_LIDL_PRODUCT_URL
--state-file PATH
```

`--url` is repeatable and preserves command-line order.

Optional arguments:

```text
--timeout-seconds POSITIVE_INTEGER
--price-drop-percentage DECIMAL_0_TO_100
--price-drop-amount NON_NEGATIVE_DECIMAL
```

Both PRICE_DROP and BACK_IN_STOCK rules are enabled. Optional price arguments
configure thresholds on the price-drop rule. Money and percentage input is
parsed directly as `Decimal` and never through `float`.

### version

`version` writes:

```text
Price Watch <version>
```

The CLI package exposes one version constant. A test keeps it synchronized
with project metadata.

### watch

Repeated interval execution is added by ADR-0011. `watch` reuses the `sync`
configuration and composition; it does not introduce a second synchronization
implementation.

### evaluate

A standalone `evaluate` command is deferred. The project has no approved
serialized Product and Rule input contract, and adding a second ad-hoc
evaluation path would duplicate workflow composition. Future introduction
requires a defined user-facing input model.

---

## Public API

The package exports:

```python
VERSION: str

main() -> int

run(
    argv: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
    *,
    delay: Delay | None = None,
) -> int
```

`main()` is the process adapter. It supplies `sys.argv`, `sys.stdout`,
`sys.stderr`, a UTC system clock and `uuid4` to `run()`.

`run()` is the deterministic programmatic boundary used by tests and future
launchers. It does not read environment variables or global streams. The
optional delay dependency is used only by the `watch` extension in ADR-0011;
existing `sync` and `version` callers remain compatible.

---

## Output and Exit Codes

Generated notifications are written by `ConsoleNotificationChannel` to
stdout. After a cycle, stdout receives one summary line containing product,
evaluation, notification, snapshot and provider-error counts.

Provider errors are written individually to stderr.

Exit codes:

- `0`: command completed without provider errors
- `1`: synchronization completed with provider errors, or a known State
  Store, Rule Engine or notification delivery failure occurred
- `2`: command-line usage or composition configuration is invalid

Help returns `0`. Parser diagnostics use the injected stderr stream.
Unexpected programming failures and invalid injected clock or identifier
factory behavior are not silently converted.

---

## Configuration and Identity

CLI arguments are parsed into frozen, slotted command values before
composition.

The two built-in rules use stable application-owned UUIDs. Notification UUIDs
come from the injected factory. One caller-supplied clock provides the cycle
timestamp and the Lidl provider timing values.

No environment variable, implicit configuration file or default state path is
used. Durable state location and monitored URLs remain explicit.

---

## Dependency Direction

```text
CLI
    |
    +--> applications.synchronization
    +--> Infrastructure implementations
    +--> Core services and Domain configuration
```

The CLI is the outer composition root. Core, Infrastructure and the reusable
synchronization package do not import `applications.cli`.

---

## Alternatives Considered

### Put synchronization steps directly in the command handler

Rejected because it would duplicate `SynchronizationWorkflow` and allow CLI
behavior to diverge from future applications.

### Read configuration from environment variables

Rejected for the first version because it introduces hidden process state and
precedence rules. Explicit arguments are sufficient for local operation.

### Use a third-party CLI framework

Rejected because the standard-library `argparse` module covers the first
command surface without adding a runtime dependency.

### Implement standalone evaluate immediately

Rejected because no stable external Product or Rule representation exists.
The complete `sync` command already performs practical evaluation.

---

## Consequences

Advantages:

- the platform is executable without custom Python code
- composition remains in the outer Application layer
- exact monetary configuration
- deterministic programmatic command boundary
- no new runtime dependency

Costs:

- configuration is command-line only
- only Lidl Parkside and console delivery are composed initially
- users must provide URLs and state path on every invocation
