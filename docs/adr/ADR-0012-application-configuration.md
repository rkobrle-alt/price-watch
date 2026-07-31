# ADR-0012: Application Configuration

## Status

Accepted

---

## Context

The complete platform can be run with `sync` and `watch`, but every execution
currently requires product URLs, persistence path, rule thresholds and
scheduler interval to be repeated as command-line arguments. This is
error-prone for long-running operation and unsuitable as the shared starting
point for future application adapters.

Configuration parsing must not introduce filesystem I/O into Core or business
logic into the CLI. Exact monetary thresholds must never pass through
`float`, and an evolving file format needs an explicit version.

---

## Decision

The first application configuration is a strict, versioned TOML document.
Responsibilities are separated as follows:

```text
core.configuration
    ConfigurationLoader Protocol
    ConfigurationError

applications.configuration
    immutable ApplicationConfig
    pure document validation and conversion

infrastructure.configuration.toml
    TomlConfigurationLoader filesystem implementation

applications.cli
    command selection and dependency composition
```

Core defines contracts only. The Infrastructure loader reads and decodes the
file. The Application parser validates the neutral mapping and produces an
immutable configuration. The CLI converts that configuration into its
existing immutable command values and composes the existing stack.

---

## Document Contract

Schema version 1 has this shape:

```toml
schema_version = 1

[provider.lidl]
product_urls = [
  "https://www.lidl.cz/example-product/p100000000",
]
timeout_seconds = 10

[state]
file = "data/price-watch-state.json"

[rules.price_drop]
percentage = "10.00"
fixed_amount = "500.00"

[scheduler]
interval_seconds = 300
```

Required values:

- `schema_version`
- `provider.lidl.product_urls`
- `state.file`

Optional values:

- `provider.lidl.timeout_seconds`, default `10`
- the `rules` table and `rules.price_drop` thresholds
- the `scheduler` table

When `[scheduler]` is present, `interval_seconds` is required. A configured
`watch` command requires the scheduler table; `sync` may use the same document
with or without it.

Thresholds are TOML strings parsed directly as `Decimal`. TOML floats are
rejected. Percentage must be finite and between 0 and 100. Fixed amount must
be finite and non-negative. Integer values reject `bool` and must be positive.

Product URLs must be a non-empty array of non-blank strings. Provider-specific
URL validation remains authoritative in `LidlParksideProvider`.

Unknown keys and tables are rejected at every documented level. Schema
versions other than integer `1` are rejected.

---

## Path Semantics

The configuration file path is explicit. There is no default path, discovery,
environment lookup or implicit user-directory configuration.

An absolute `state.file` is preserved. A relative `state.file` is interpreted
relative to the directory containing the TOML file. Parsing does not require
the state path to exist.

---

## CLI Integration

Both commands accept configuration mode:

```text
price-watch sync --config PATH
price-watch watch --config PATH [--max-cycles POSITIVE_INTEGER]
```

Configuration mode and direct configuration arguments are mutually exclusive.
The first version has no general CLI-over-file precedence rules. For `watch`,
`--max-cycles` remains an allowed process-lifetime bound and is never stored in
the file.

Existing direct invocations remain unchanged and backward compatible.

`applications.cli.run()` gains the optional keyword-only dependency:

```python
configuration_loader: ConfigurationLoader | None = None
```

The process adapter supplies `TomlConfigurationLoader`. Programmatic callers
need the dependency only when using `--config`.

---

## Public API

```python
class ConfigurationLoader(Protocol):
    def load(self, path: Path) -> Mapping[str, object]: ...
```

```python
class ConfigurationError(RuntimeError): ...
```

```python
@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    product_urls: tuple[str, ...]
    state_file: Path
    timeout_seconds: int
    price_drop_percentage: Decimal | None
    price_drop_amount: Decimal | None
    interval: timedelta | None
```

```python
parse_configuration(
    document: Mapping[str, object],
    base_directory: Path,
) -> ApplicationConfig
```

```python
TomlConfigurationLoader.load(path: Path) -> Mapping[str, object]
```

---

## Error Handling

Invalid public API argument types raise `TypeError`.

`ConfigurationError` represents:

- filesystem and UTF-8 failures while loading configuration
- malformed TOML
- unsupported schema versions
- missing, unknown or invalid document values
- a missing scheduler interval for configured `watch`

The original exception is chained for loader failures. CLI configuration
errors write `error: MESSAGE` to stderr and return exit code `2`. Unexpected
programming failures propagate.

---

## Security Scope

Schema version 1 contains no credentials or secrets. Future notification
credentials require a separate decision defining a secret source; this ADR
does not authorize storing secrets in TOML or reading environment variables.
ADR-0013 consequently requires an explicitly injected Home Assistant token;
the future Home Assistant App process boundary will own Supervisor-token
access.

---

## Dependency Direction

```text
CLI
    +--> applications.configuration
    +--> infrastructure.configuration.toml

applications.configuration --> core.configuration
infrastructure.configuration.toml --> core.configuration
```

Core performs no file access and imports neither Applications nor
Infrastructure. The reusable Application parser imports no concrete loader.
Infrastructure does not import Applications or CLI.

---

## Alternatives Considered

### Read TOML directly in the CLI parser

Rejected because argument parsing would acquire filesystem and schema
responsibilities, making configuration unavailable to other applications.

### Use environment variables

Rejected for structured product lists and rules because naming, ordering and
type conversion become opaque. Secret handling remains a separate concern.

### Permit arbitrary CLI overrides

Rejected for the first version because precedence and partial overrides create
an additional configuration language. Mutually exclusive modes are explicit.

### Use JSON or YAML

JSON is verbose for operator-authored configuration. YAML requires a runtime
dependency and has a larger parsing surface. Python 3.13 includes `tomllib`.

---

## Consequences

Advantages:

- repeatable application startup from one explicit file
- exact decimal thresholds
- strict typo detection and versioned evolution
- filesystem side effects remain in Infrastructure
- one pure configuration model reusable by future applications
- existing CLI invocations remain compatible

Costs:

- no partial command-line overrides
- schema changes require an explicit new version or migration decision
- credentials and secret sources remain intentionally unresolved
