# STORY-013: Home Assistant Application

## Goal

Package and execute Price Watch as a minimal Home Assistant App according to
ADR-0014, using the existing Lidl workflow, durable state and SMTP-backed
`notify.gmail_parkside_kobrle_fomei_com` delivery.

---

## Scope

This story includes:

- pure Home Assistant App-option configuration
- JSON option loading
- Supervisor token injection at the process boundary
- Home Assistant synchronization and scheduler composition
- Home Assistant App repository metadata and operator documentation
- an amd64/aarch64 container definition and image publishing workflow
- unit, architecture, packaging and boundary integration tests

This story does not include:

- changes to Domain, Provider SDK, Rule Engine or synchronization contracts
- direct SMTP credentials or delivery
- CLI Home Assistant channel selection
- retries, notification deduplication, dashboards, entities or ingress
- pushing, publishing or installing external artifacts

---

## Package Structure

Create or replace:

```text
applications/homeassistant/
    __init__.py
    __main__.py
    configuration.py
    composition.py
    main.py

infrastructure/configuration/json/
    __init__.py
    loader.py

homeassistant/price_watch/
    CHANGELOG.md
    DOCS.md
    README.md
    config.yaml

tests/unit/homeassistant_app/
    __init__.py
    test_configuration.py
    test_composition.py
    test_main.py
    test_packaging.py
    test_public_api.py

tests/integration/test_homeassistant_app.py

repository.yaml
Dockerfile
.dockerignore
.github/workflows/publish-homeassistant.yml
```

Move the canonical version value to `applications/version.py` and retain the
existing `applications.cli.VERSION` export. Update metadata to `0.13.0` only
in the release commit.

---

## Public API

Export through `applications.homeassistant`:

- `HomeAssistantConfig`
- `parse_homeassistant_options`
- `run`
- `main`

Export through `infrastructure.configuration.json`:

- `JsonConfigurationLoader`

Signatures and fields must exactly match ADR-0014. Every public object has
explicit typing and documentation.

---

## Configuration

`parse_homeassistant_options()` accepts only:

```text
product_urls
notify_entity
interval_seconds
timeout_seconds
price_drop_percentage
price_drop_amount
notification_title
```

The first three are required. Optional defaults are defined by ADR-0014.
Unknown keys, missing values and malformed values raise `ConfigurationError`
with the option name in the message. Decimal thresholds are strings and reuse
the validation semantics of application configuration. `data_directory` is a
`Path`; state is always `<data_directory>/state.json`.

`HomeAssistantConfig` is frozen and slotted. Direct construction validates
its member types, the notify entity form and non-blank title.

`JsonConfigurationLoader` requires a `Path`, reads UTF-8 JSON and returns a
mapping. Filesystem, Unicode, JSON syntax and non-object-root failures raise
`ConfigurationError` with chaining where an underlying exception exists.
Unexpected failures propagate.

---

## Runtime Composition

The App composes:

- `LidlParksideProvider` with `UrllibTextHttpClient`
- `JsonStateStore` at the fixed App data path
- registered `PriceDropEvaluator` and `BackInStockEvaluator`
- the same stable rule identifiers as the CLI
- `NotificationEngine`
- `UrllibHomeAssistantClient` at `http://supervisor/core/api`
- `HomeAssistantNotificationChannel`
- `SynchronizationWorkflow`
- `IntervalScheduler` and injected `Delay`

Rules have application-neutral names. Existing CLI behavior and public API
remain unchanged.

Each cycle writes a concise synchronization summary and each provider error.
Provider-error cycles do not stop the scheduler. Known operational errors,
configuration failures and interruption map exactly as ADR-0014 specifies.

`main()` loads `/data/options.json`, requires a non-blank
`SUPERVISOR_TOKEN`, supplies UTC time, `uuid4`, `SystemDelay` and process
streams, then calls `run()`. It never prints the token.

---

## App Packaging

`repository.yaml` identifies the existing GitHub repository.

`config.yaml`:

- uses slug `price_watch` and version `0.13.0`
- supports `amd64` and `aarch64`
- enables `homeassistant_api: true`
- starts automatically as an application
- references `ghcr.io/rkobrle-alt/price-watch`
- defines defaults including `notify.gmail_parkside_kobrle_fomei_com`
- exposes only the option schema in this story
- requests no ingress, ports, host networking, devices, mounts, Docker API,
  Supervisor API or privileged access

The root Dockerfile uses Python 3.13+, copies the existing source packages and
starts `python -m applications.homeassistant`. It contains no credential.

The publishing workflow runs only for version tags, builds linux/amd64 and
linux/arm64 from the repository root and publishes semantic-version tags to
GHCR using repository-scoped credentials.

---

## Dependency Rules

- Core and Domain do not change.
- Infrastructure imports no Applications.
- reusable synchronization and scheduler packages import no Home Assistant
  application or concrete Infrastructure.
- `applications.homeassistant` is the only Python package that combines App
  options, Supervisor access and concrete HA delivery.
- `applications.cli` does not import `applications.homeassistant`.
- no Home Assistant Python runtime dependency is introduced.

---

## Tests

Tests must cover:

- immutability and every `HomeAssistantConfig` invariant
- valid options, defaults, unknown/missing keys and every invalid scalar
- exact Decimal preservation and state-path derivation
- JSON loader success and all defined failure translations
- public exports, typing, documentation and dependency direction
- exact workflow composition, REST root, entity, title and stable rules
- immediate and repeated cycles without real wait, HTTP or Home Assistant
- provider-error continuation and final status
- known operational failures, interruption and unexpected failure behavior
- missing, blank and secret-safe Supervisor token handling
- exact App manifest permissions, defaults, version and architectures
- repository metadata, container entry point and publishing trigger
- absence of credentials, SMTP configuration and privileged App permissions

The integration test uses a temporary options document and state directory,
real JSON loader, real Home Assistant App parser, Lidl parser, JSON State
Store, Rule Engine, workflow, scheduler and Home Assistant notification
channel with fake HTTP boundaries. No network or sleep occurs.

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0014 and every prior accepted ADR are followed.
- the App starts from Supervisor options and injected token.
- the first observation creates durable state in App storage.
- a later cycle can notify `notify.gmail_parkside_kobrle_fomei_com` about a detected change.
- token and SMTP credentials are never persisted or logged.
- Core, Domain and reusable workflow contracts remain unchanged.
- CLI direct and TOML modes remain backward compatible.
- public APIs are exported through `__init__.py`.
- packaging declares only required Home Assistant permissions.
- no TODOs, placeholders, pass statements, commented code or dead code remain.
- all tests pass with 100% statement and branch coverage.
- all changes are visible in Git and organized into logical commits.
