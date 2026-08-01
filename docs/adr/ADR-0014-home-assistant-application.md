# ADR-0014: Home Assistant Application

## Status

Accepted

---

## Context

ADR-0013 provides Home Assistant REST communication and notification delivery,
but no executable process composes those adapters. Price Watch must run
continuously under Home Assistant Supervisor, retain state across restarts and
reuse the existing SMTP-backed notify entity without storing SMTP credentials.

The deployment boundary must obtain a Supervisor token and App options without
introducing environment or filesystem access into Core. The existing CLI must
remain an independent console composition.

---

## Decision

The Home Assistant composition root belongs to:

```text
applications.homeassistant
```

It composes the existing Lidl provider, JSON State Store, Rule Engine,
Notification Engine, `HomeAssistantNotificationChannel`, synchronization
workflow and interval scheduler. It does not reproduce their business logic.

The process runs immediately and then at a fixed delay using the existing
`IntervalScheduler`. Cycles never overlap.

---

## App Options

Home Assistant Supervisor stores non-secret App options in
`/data/options.json`. The outer process loads that document through:

```text
infrastructure.configuration.json.JsonConfigurationLoader
```

The pure `applications.homeassistant` parser accepts:

- required `product_urls`: a non-empty ordered list of Lidl product URLs
- required `notify_entity`: a lowercase `notify.<object_id>` entity
- required positive `interval_seconds`
- optional positive `timeout_seconds`, default `10`
- optional decimal-string `price_drop_percentage`
- optional decimal-string `price_drop_amount`
- optional non-blank `notification_title`, default `Price Watch`

Unknown options are rejected. Decimal values never pass through `float`.
General synchronization values are represented by the existing immutable
`ApplicationConfig`.

State storage is intentionally fixed to `/data/state.json`. The Supervisor
preserves `/data` for the installed App, so users cannot accidentally select a
non-persistent or shared file. The App provides no state-path option.

---

## Supervisor Access

The process adapter reads `SUPERVISOR_TOKEN` and supplies it directly to
`UrllibHomeAssistantClient` with the fixed internal API root:

```text
http://supervisor/core/api
```

The App manifest enables `homeassistant_api: true`.

The token is never accepted as an App option, persisted, logged, included in
an exception message or passed to Core. Missing or blank tokens prevent
startup with a configuration diagnostic.

---

## Public API

`applications.homeassistant` exports:

```python
@dataclass(frozen=True, slots=True)
class HomeAssistantConfig:
    application: ApplicationConfig
    notify_entity: str
    notification_title: str = "Price Watch"
```

```python
parse_homeassistant_options(
    document: Mapping[str, object],
    data_directory: Path,
) -> HomeAssistantConfig
```

```python
run(
    options: Mapping[str, object],
    access_token: str,
    stdout: TextIO,
    stderr: TextIO,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
    delay: Delay,
    *,
    data_directory: Path = Path("/data"),
    max_cycles: int | None = None,
) -> int
```

```python
main() -> int
```

`max_cycles` is a deterministic programmatic test bound. The Supervisor
process omits it and runs until interruption or an operational failure.

The canonical application `VERSION` moves to `applications.version`.
`applications.cli.VERSION` remains a backward-compatible re-export.

`infrastructure.configuration.json` exports:

```python
JsonConfigurationLoader.load(path: Path) -> Mapping[str, object]
```

---

## Failure Semantics

- invalid public argument types raise `TypeError`
- invalid App options raise `ConfigurationError`
- App option or missing-token startup failures return `2`
- State Store, Rule Engine, notification and scheduler failures return `1`
- provider errors are reported per cycle and do not stop later cycles
- a finite programmatic run returns `1` when any cycle reported provider errors
- interruption returns `130`
- unexpected programming failures propagate

Existing delivery-before-persistence and at-least-once behavior remain
unchanged.

---

## Packaging and Distribution

The repository is a Home Assistant App repository and contains:

- root `repository.yaml`
- `homeassistant/price_watch/config.yaml` and operator documentation
- a root Dockerfile that packages the existing Python source without copying
  or forking it into the App directory
- a GitHub Actions workflow that publishes one amd64/aarch64 OCI image to
  `ghcr.io/rkobrle-alt/price-watch`

The App manifest references the multi-architecture image and declares only
the Home Assistant Core API permission. It exposes no port, ingress, host
network, device, Docker or Supervisor API permission.

Publishing, pushing Git commits and installing the App are external release
operations and do not occur as an implicit implementation side effect.

---

## Dependency Direction

```text
applications.homeassistant
    +--> applications.configuration
    +--> applications.scheduler
    +--> applications.synchronization
    +--> Infrastructure implementations
    +--> Core contracts and services

infrastructure.configuration.json --> core.configuration
```

Core and reusable workflows do not import the Home Assistant application.
Infrastructure does not import Applications. The CLI does not import the Home
Assistant application and retains console delivery.

---

## Alternatives Considered

### Generate TOML from a shell startup script

Rejected because it would create another configuration transformation at an
untested shell boundary and make Home Assistant options indirect.

### Store the Supervisor token in App options

Rejected because Supervisor already injects a short-lived credential and App
options are persistent configuration.

### Duplicate Python source inside the App directory

Rejected because two source trees would drift. The published container is
built from the repository root.

### Add Home Assistant delivery to the existing CLI

Rejected because the Supervisor token and `/data` lifecycle belong to a
distinct process boundary. The reusable workflow already permits a separate
composition root.

---

## Consequences

Advantages:

- practical continuous execution under Home Assistant
- reuse of the existing SMTP notify entity
- persistent App-owned state
- no user-managed Home Assistant token or SMTP credential
- unchanged Core, Domain and workflow contracts
- one Python source tree for CLI and container execution

Costs:

- App options form a second external configuration representation
- published installation depends on the GHCR image release workflow
- delivery remains at-least-once and has no retry or deduplication

---

## References

- https://developers.home-assistant.io/docs/apps/configuration/
- https://developers.home-assistant.io/docs/apps/communication/
- https://developers.home-assistant.io/docs/apps/repository/
- https://developers.home-assistant.io/docs/apps/publishing/
