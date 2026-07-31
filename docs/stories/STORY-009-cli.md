# STORY-009: Command-Line Interface

## Goal

Implement the first executable CLI according to ADR-0010. The CLI must compose
the existing Lidl, JSON persistence, Rule Engine, Notification Engine and
Synchronization Workflow implementations into one practical `sync` command.

---

## Package Structure

Create:

```text
applications/cli/
    __init__.py
    __main__.py
    arguments.py
    composition.py
    main.py
    parser.py
    version.py

tests/unit/cli/
    __init__.py
    helpers.py
    test_architecture.py
    test_arguments.py
    test_composition.py
    test_entrypoint.py
    test_main.py
    test_parser.py
    test_public_api.py

tests/integration/
    test_cli_sync.py
```

Modify `pyproject.toml` to expose the `price-watch` console script and include
the CLI version in the project release update.

---

## Public API

Export through `applications.cli`:

- `VERSION`
- `main`
- `run`

Signatures:

```python
main() -> int
```

```python
run(
    argv: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
) -> int
```

Every public object must have explicit typing and documentation.

---

## Commands

### version

```text
price-watch version
```

Writes exactly:

```text
Price Watch 0.9.0\n
```

and returns `0`.

### sync

```text
price-watch sync \
    --state-file PATH \
    --url HTTPS_LIDL_PRODUCT_URL \
    [--url HTTPS_LIDL_PRODUCT_URL ...] \
    [--timeout-seconds INTEGER] \
    [--price-drop-percentage DECIMAL] \
    [--price-drop-amount DECIMAL]
```

Requirements:

- at least one `--url` is required
- `--state-file` is required and converted to `Path` without filesystem access
  during parsing
- URL order and duplicates are preserved for provider validation
- timeout defaults to `10` and must be a positive integer other than `bool`
- percentage is optional and must be a finite Decimal from 0 through 100
- fixed amount is optional and must be a finite non-negative Decimal
- numeric values never pass through `float`

The command composes exactly:

- `UrllibTextHttpClient` with `PriceWatch/0.9.0` user agent
- `LidlParksideProvider`
- `JsonStateStore`
- `EvaluatorRegistry` with `PriceDropEvaluator` and
  `BackInStockEvaluator`
- `RuleEngine`
- `NotificationEngine`
- `ConsoleNotificationChannel` using injected stdout
- `SynchronizationWorkflow`

Create two enabled, immutable rules in this order:

1. PRICE_DROP with the supplied optional parameters
2. BACK_IN_STOCK without parameters

Both rule IDs are stable application constants.

Read one timezone-aware cycle timestamp from the injected clock before
running the workflow. The Lidl provider uses the same injected clock for its
own timing reads. Clock and identifier-factory return validation remains with
the existing called APIs.

---

## Output

Generated notification lines are written and flushed by
`ConsoleNotificationChannel`.

After successful workflow return, write and flush exactly one summary line:

```text
sync complete: products=P evaluations=E notifications=N snapshots=S provider_errors=R\n
```

For every provider error, write and flush to stderr:

```text
provider error: MESSAGE\n
```

Provider error order follows `SynchronizationResult.provider_errors`.

---

## Exit Codes and Error Handling

- return `0` when `sync` completes without provider errors
- return `1` when `sync` returns one or more provider errors
- return `1` for `StateStoreError`, `RuleError` or `NotificationError`; write
  `error: MESSAGE\n` to stderr
- return `2` for parser errors or invalid composition values; write the
  diagnostic to injected stderr
- help writes to injected stdout and returns `0`
- invalid public `run()` argument types raise `TypeError`
- unexpected provider, clock, UUID-factory and programming failures propagate
  unchanged

Do not add retries, logging, environment configuration or traceback
suppression.

---

## Process Adapter

`main()` calls `run()` with:

- `sys.argv[1:]`
- `sys.stdout`
- `sys.stderr`
- `lambda: datetime.now(UTC)`
- `uuid4`

`__main__.py` exits using the integer returned by `main()`.

---

## Dependency Rules

The CLI may import only the dependencies approved by ADR-0010.

Core, Infrastructure and `applications.synchronization` must not import
`applications.cli`.

The CLI must not implement provider parsing, persistence encoding, price-drop
comparison, availability transitions or notification generation.

No existing public API may be changed.

---

## Tests

Unit tests must not use network, filesystem, environment or global streams.
They must cover:

- immutable command arguments and field validation
- every parser command, option, default and validation branch
- help and injected parser streams
- exact Decimal preservation
- exact composition types, evaluator order, rule order and thresholds
- stable rule IDs and version synchronization
- `version` output
- summary and provider-error output
- every exit-code branch
- known operational error conversion
- unexpected failure propagation
- public API, entry point and console-script metadata
- dependency boundaries and absence of business logic

The integration test must use fake HTTP content with real Lidl parsing,
`JsonStateStore`, Rule Engine, workflow and console delivery across two CLI
runs. It must not access the network.

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0010 and all earlier accepted ADRs are followed.
- `price-watch sync` executes one complete synchronization cycle.
- state survives a new CLI run through `JsonStateStore`.
- a later price drop and return to stock produce notifications.
- money and thresholds never use `float`.
- CLI contains composition and presentation only.
- all nondeterministic dependencies are confined to `main()`.
- public APIs are exported through `__init__.py`.
- project metadata exposes the console script.
- no TODOs, placeholders, pass statements, commented-out code or dead code
  remain.
- all tests pass with 100% statement and branch coverage.
