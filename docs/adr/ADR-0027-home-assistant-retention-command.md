# ADR-0027: Home Assistant Retention Command

## Status

Accepted

## Context

ADR-0025 provides backup-protected observation retention through the CLI and
ADR-0026 projects a selected read-only plan into Home Assistant. The operator
has approved a 90-day window and needs an explicit Home Assistant action which
can apply the currently reviewed plan without opening a network port or
turning retention into scheduled behavior.

REST-created sensor states cannot register commands or button entities. A
persistent App option is also an unsafe trigger: the option survives restart
and could repeat a destructive operation. Home Assistant Apps instead support
one-shot data delivery through the native `hassio.addon_stdin` action when the
manifest enables `stdin`.

Monitoring and retention both access the shared SQLite database. They must
never run concurrently even though standard-input commands arrive
independently of the fixed-delay monitoring scheduler.

## Decision

The Home Assistant App accepts one strict JSON-lines maintenance command over
Supervisor-managed standard input. The command is disabled unless catalog
mode and `retention_preview_days` are configured.

The external command shape is:

```json
{
  "command": "apply_retention",
  "confirmation": "APPLY_RETENTION",
  "expected_removable_observation_count": 123
}
```

The complete object is required and unknown keys are rejected. The expected
count must be a non-negative integer and must reject `bool`. The confirmation
is deliberately exact and case-sensitive.

The command uses the configured preview window. At command time the
Application computes `cutoff = timestamp - retention_preview_days`, obtains a
fresh plan and compares its removable count with the command. A mismatch is a
stale-plan outcome and performs no backup or deletion. A matching zero plan is
a no-change outcome and likewise performs no mutation.

For a matching positive plan the Application obtains a unique timestamped
path below `/data/retention-backups` and invokes the existing
`ObservationRetentionManager.apply()` exactly once. The SQLite adapter retains
ADR-0025 semantics: a complete backup is written before transactional deletion,
the destination must not exist and no vacuum is run.

## Serialization

The App owns one process-wide maintenance lock. Every monitoring cycle and
every accepted maintenance command acquires the same lock around database
work. A command waits for an active cycle to finish; a cycle waits for an
active command. No SQLite maintenance operation overlaps catalog discovery,
refresh, notification reservation, digest reservation or status queries.

A daemon command-listener thread performs blocking reads from the injected
standard-input stream. It parses one line at a time and invokes the serialized
Application processor. End-of-file stops only the listener, not monitoring.
Malformed or failed commands are written to the App error stream and do not
stop the scheduler. Unexpected programming failures are not silently
translated.

## Public API

`applications.homeassistant` exports:

```python
class MaintenanceCommandStatus(str, Enum):
    STALE_PLAN = "stale_plan"
    NO_CHANGES = "no_changes"
    APPLIED = "applied"
```

```python
@dataclass(frozen=True, slots=True)
class HomeAssistantMaintenanceCommand:
    expected_removable_observation_count: int
```

```python
@dataclass(frozen=True, slots=True)
class MaintenanceCommandResult:
    status: MaintenanceCommandStatus
    timestamp: datetime
    retention_days: int
    plan: ObservationRetentionPlan
    removed_observation_count: int = 0
    backup_file: Path | None = None
```

```python
class MaintenanceCommandError(RuntimeError): ...
```

```python
parse_maintenance_command(line: str) -> HomeAssistantMaintenanceCommand
```

```python
MaintenanceCommandProcessor(
    retention_manager: ObservationRetentionManager,
    retention_days: int,
    backup_file_factory: Callable[[datetime], Path],
)
```

```python
process(
    command: HomeAssistantMaintenanceCommand,
    timestamp: datetime,
) -> MaintenanceCommandResult
```

The existing `run()` boundary gains optional keyword-only
`command_input: TextIO | None = None`. `main()` supplies `sys.stdin`; existing
programmatic callers remain compatible when the argument is omitted.

`infrastructure.persistence.sqlite` exports
`TimestampedRetentionBackupFileFactory(directory: Path)`. Calling it creates
the configured directory when necessary and returns a non-existing UTC-
timestamped SQLite path. Filesystem failures raise `StateStoreError`.

## Home Assistant Representation

The App manifest enables only `stdin: true`; existing API permission remains
unchanged. It adds no ingress, port, host mapping, Supervisor API permission,
MQTT dependency or custom integration.

`sensor.price_watch_maintenance` changes its `apply_available` attribute to
`true` when the command listener is composed. Preview-only construction keeps
the backward-compatible default `false`.

Successful command outcomes are written to the process log. After an applied
or no-change result the existing preview is recalculated and published so the
sensor exposes current total, removable, retained and protected counts.

## Errors and Safety

- invalid public argument types raise `TypeError`;
- malformed JSON, unknown fields and invalid command values raise
  `MaintenanceCommandError`;
- stale-plan and zero-plan outcomes do not create directories or backups;
- `StateStoreError` retains the persistence boundary and never gets reported
  as success;
- a Home Assistant publication failure is logged and does not alter the
  already completed retention result;
- duplicate user actions are safe because every action replans; an immediate
  duplicate normally produces no changes;
- the App never schedules a command and never applies retention merely because
  preview is enabled.

## Dependency Direction

```text
Home Assistant hassio.addon_stdin
    |
    v
applications.homeassistant command listener and processor
    +--> core.state retention contract
    +--> infrastructure.persistence.sqlite retention and backup adapters
    +--> infrastructure.homeassistant preview publisher
```

Core, Domain, Provider SDK and Rule Engine remain unchanged and deterministic.
Infrastructure does not import Applications.

## Alternatives Considered

### Persistent apply option

Rejected because App options survive restart and require an additional durable
one-shot ledger to prevent accidental repetition.

### REST-created button state

Rejected because `/api/states` creates representations, not registered
entities or callable services.

### Ingress HTTP UI

Deferred because a command page would add an HTTP server, ingress lifecycle and
another authenticated surface when Supervisor stdin already supplies a native
one-shot boundary.

### Automatic age-based retention

Rejected because deletion remains an explicit operator action. A configured
preview window is not consent to mutate history.

## Consequences

The operator can apply a freshly revalidated plan from a Home Assistant script
or dashboard action while every destructive operation remains explicit,
serialized and backed up. The cost is one small command thread, strict action
configuration and a backup file retained in persistent App storage.
