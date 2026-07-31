# Command-Line Interface Architecture

## Purpose

The CLI is the first user-facing composition root for executing Price Watch
from a terminal.

---

## Package

```text
applications/cli/
    __init__.py
    __main__.py
    arguments.py
    composition.py
    main.py
    parser.py
    version.py
```

Responsibilities:

- `arguments.py` contains immutable parsed command values
- `parser.py` owns `argparse` configuration and usage diagnostics
- `composition.py` assembles the approved concrete synchronization stack
- `main.py` dispatches commands and maps known outcomes to exit codes
- `version.py` owns the CLI version constant
- `__main__.py` adapts the package to `python -m`
- `__init__.py` exports the public API

---

## Public API

```python
VERSION: str
main() -> int
run(argv, stdout, stderr, clock, notification_id_factory) -> int
```

`run()` receives every nondeterministic process dependency explicitly.
`main()` supplies real process dependencies only at the outermost boundary.

---

## Sync Composition

```text
CLI arguments
    |
    v
LidlParksideProvider + UrllibTextHttpClient
    |
    v
SynchronizationWorkflow
    +--> JsonStateStore
    +--> RuleEngine
    |       +--> PriceDropEvaluator
    |       +--> BackInStockEvaluator
    +--> NotificationEngine
    +--> ConsoleNotificationChannel
    |
    v
SynchronizationResult
    |
    +--> notification and summary output
    +--> provider diagnostics
    +--> process exit code
```

The command handler invokes the reusable workflow once. It never loads state,
evaluates rules, generates notifications or saves snapshots itself.

---

## Arguments

`sync` requires one or more `--url` values and one `--state-file` path.

Optional timeout and price thresholds are validated while parsing. Decimal
converters reject non-finite or out-of-range values before composition.

Parsed commands are immutable and contain no `argparse.Namespace` outside the
parser module.

---

## Error Boundary

Usage and composition configuration errors return `2` after writing a concise
diagnostic to stderr.

Known operational subsystem errors return `1`. Provider partial failures are
already represented by `SynchronizationResult`; the CLI writes them and also
returns `1`.

Unexpected exceptions propagate for visibility.

---

## Dependency Rules

`applications.cli` may depend on:

- `applications.synchronization`
- public Core and Domain APIs
- approved concrete Infrastructure implementations
- Python standard library process facilities

No inner package may depend on the CLI.

The CLI contains no HTML parsing, money comparison, availability transition,
serialization or notification-generation logic.
