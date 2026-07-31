# STORY-011: Application Configuration

## Goal

Implement strict TOML application configuration according to ADR-0012 and
allow existing `sync` and `watch` commands to use it without changing their
direct-argument behavior.

---

## Package Structure

Create:

```text
core/configuration/
    __init__.py
    contract.py
    exceptions.py

applications/configuration/
    __init__.py
    model.py
    parser.py

infrastructure/configuration/
    __init__.py
    toml/
        __init__.py
        loader.py

applications/cli/configuration.py

tests/unit/configuration/
    __init__.py
    test_application_config.py
    test_parser.py
    test_public_api.py
    test_toml_loader.py

tests/integration/test_cli_configuration.py
```

Extend existing CLI argument, parser, main, architecture and entry-point tests.
Update project metadata to version `0.11.0` only in the release commit.

---

## Public API

Export through `core.configuration`:

- `ConfigurationError`
- `ConfigurationLoader`

Export through `applications.configuration`:

- `ApplicationConfig`
- `parse_configuration`

Export through `infrastructure.configuration.toml`:

- `TomlConfigurationLoader`

Signatures and fields must exactly match ADR-0012. Every public object has
explicit typing and documentation.

Extend `applications.cli.run()` with the backward-compatible keyword-only
parameter:

```python
configuration_loader: ConfigurationLoader | None = None
```

Do not change the existing `applications.cli.__all__` export list.

---

## Application Model

`ApplicationConfig` is a frozen, slotted dataclass containing:

```python
product_urls: tuple[str, ...]
state_file: Path
timeout_seconds: int = 10
price_drop_percentage: Decimal | None = None
price_drop_amount: Decimal | None = None
interval: timedelta | None = None
```

Its invariants are:

- `product_urls` is a non-empty tuple of non-blank strings
- `state_file` is a `Path`
- `timeout_seconds` is a positive `int` other than `bool`
- percentage is `None` or a finite `Decimal` from 0 through 100
- fixed amount is `None` or a finite non-negative `Decimal`
- interval is `None` or a positive `timedelta`

Invalid types raise `TypeError`; invalid values raise `ValueError` when the
model is constructed directly.

---

## Pure Document Parser

`parse_configuration()` performs no I/O. It validates a `Mapping[str, object]`
against schema version 1 and returns `ApplicationConfig`.

It accepts only these keys:

```text
root: schema_version, provider, state, rules, scheduler
provider: lidl
provider.lidl: product_urls, timeout_seconds
state: file
rules: price_drop
rules.price_drop: percentage, fixed_amount
scheduler: interval_seconds
```

Rules:

- root `schema_version`, `provider` and `state` are required
- schema version must be the integer `1`, not `bool`
- every table is a mapping with string keys
- required nested tables and values must be present
- unknown keys are rejected, including in optional tables
- product URL order is preserved
- timeout defaults to `10`
- missing rule thresholds become `None`
- threshold values must be strings parsed directly with `Decimal`
- invalid, non-finite and out-of-range decimals raise `ConfigurationError`
- `[scheduler]`, when present, requires a positive integer
  `interval_seconds`
- an absent scheduler table produces `interval=None`
- `base_directory` must be a `Path`
- a relative state path is prefixed with `base_directory`
- an absolute state path is preserved
- blank state paths are rejected

All document-shape, schema and value failures raise `ConfigurationError` with
a message identifying the failing dotted path. Exceptions raised by direct
`ApplicationConfig` construction are translated to `ConfigurationError` by
the parser.

---

## TOML Loader

`TomlConfigurationLoader.load()`:

- requires a `Path`; invalid types raise `TypeError`
- reads the file as UTF-8 using standard-library facilities
- parses with `tomllib`
- returns the decoded mapping without application-schema validation
- wraps `OSError`, `UnicodeDecodeError` and `tomllib.TOMLDecodeError` in
  `ConfigurationError`
- preserves the original exception as `__cause__`
- performs no path discovery, environment access or caching

---

## CLI Argument Modes

Supported forms:

```text
price-watch sync --config PATH
price-watch watch --config PATH [--max-cycles POSITIVE_INTEGER]
```

Existing direct forms remain supported exactly as in STORY-009 and STORY-010.

For both commands, `--config` cannot be combined with:

- `--url`
- `--state-file`
- `--timeout-seconds`
- `--price-drop-percentage`
- `--price-drop-amount`
- `--interval-seconds`

Without `--config`, all previously required direct arguments remain required.
`watch --config` permits `--max-cycles`, whose existing validation and
semantics are unchanged.

The parser produces new frozen, slotted internal command values:

```python
SyncConfigurationArguments(config_file: Path)
WatchConfigurationArguments(config_file: Path, max_cycles: int | None)
```

---

## CLI Resolution and Execution

Create an internal `applications.cli.configuration` module that converts the
two configuration command values into existing `SyncArguments` or
`WatchArguments` by:

1. loading the explicit path through the injected `ConfigurationLoader`
2. calling `applications.configuration.parse_configuration()` with the TOML
   file's parent directory
3. copying the application values into existing CLI command values
4. requiring `ApplicationConfig.interval` for `watch`
5. applying only the parsed CLI `max_cycles` process bound

The existing composition and execution paths then run unchanged.

Missing `configuration_loader` for a configuration command raises `TypeError`.
An optionally supplied loader is structurally validated by public `run()` even
for other commands.

`ConfigurationError` is written as `error: MESSAGE\n` and returns `2`.
Existing parser, composition, operational and unexpected-error semantics do
not change.

`main()` supplies one `TomlConfigurationLoader` in addition to its existing
process dependencies.

---

## Dependency Rules

- Core configuration contains contracts only and performs no I/O.
- Application configuration imports only standard-library and Core contracts.
- Infrastructure TOML imports only standard-library and Core configuration.
- CLI is the only package that imports both the application parser and the
  concrete Infrastructure loader.
- Configuration packages contain no provider, rule, persistence,
  notification or scheduling business logic.
- Existing Domain, Provider SDK, Rule Engine, State Store, Notification,
  Synchronization Workflow and Scheduler public APIs remain unchanged.

---

## Tests

Unit tests must cover:

- immutability and every `ApplicationConfig` invariant branch
- public exports, typing, documentation and Protocol conformance
- complete valid documents and every optional default
- relative and absolute state paths
- exact decimal preservation and rejection of TOML floats
- missing and unknown keys at every table level
- invalid table, scalar, sequence, integer and decimal types
- unsupported schema versions
- TOML filesystem, encoding and syntax error translation
- loader unexpected-error propagation
- configuration and direct CLI modes
- every prohibited mixed-argument form
- configured `sync` and `watch` resolution
- required scheduler configuration for `watch`
- allowed `--max-cycles` process bound
- missing and invalid injected loader behavior
- configuration error exit mapping
- unchanged direct CLI behavior
- dependency direction and absence of filesystem I/O outside Infrastructure

The integration test uses a real temporary TOML file, real
`TomlConfigurationLoader`, Lidl parsing, `JsonStateStore`, Rule Engine,
workflow, interval scheduler and console delivery across two scheduled cycles.
It uses fake HTTP content and fake delay, with no network or real sleep.

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0012 and every earlier accepted ADR are followed.
- one TOML document configures both `sync` and `watch`.
- file loading exists only in Infrastructure.
- application parsing is deterministic and side-effect free.
- relative state paths resolve against the TOML directory.
- unknown keys and TOML monetary floats are rejected.
- direct CLI invocations remain backward compatible.
- no general CLI override precedence is introduced.
- Core remains deterministic and independent.
- every public API is exported through `__init__.py`.
- no secrets, environment access, TODOs, placeholders, pass statements,
  commented code or dead code are introduced.
- all tests pass with 100% statement and branch coverage.
