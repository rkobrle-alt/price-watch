# ADR-0026: Home Assistant Retention Preview

## Status

Accepted

ADR-0027 supersedes only the earlier absence of an App command. Preview remains
read-only during every monitoring cycle; explicit Supervisor-stdin composition
may advertise `apply_available: true` and invoke ADR-0025 after replanning.

## Context

ADR-0025 provides an explicit CLI-only retention operation with read-only
planning and backup-protected application. Home Assistant already reports
observation growth and reclaimable SQLite pages, but an operator cannot see
how a selected age boundary would affect retained history without leaving the
Home Assistant environment.

The current App publishes native state representations but does not register
commands or services. Exposing deletion through a synthetic button or an
ordinary state entity would misrepresent Home Assistant semantics and weaken
the explicit backup requirement.

## Decision

Add an optional, read-only retention preview to Home Assistant catalog mode.
The App option is:

```text
retention_preview_days: positive integer
```

Omitting the option disables preview and creates no maintenance state. The
option is valid only in catalog mode and intentionally has no packaged
default. Existing option documents remain unchanged.

When enabled, every successfully completed catalog cycle calculates a cutoff
from the injected timezone-aware cycle timestamp minus the configured whole
days. It invokes only `ObservationRetentionManager.plan()` and publishes:

```text
sensor.price_watch_maintenance
```

The sensor state is the removable observation count. Attributes contain the
check timestamp, cutoff, retention days, total, removable, retained and
protected observation counts, application version and an explicit
`apply_available: false` marker.

Home Assistant never invokes `ObservationRetentionManager.apply()`, creates a
backup, deletes observations, compacts SQLite or schedules maintenance.

## Public API

`HomeAssistantConfig` gains the backward-compatible field:

```python
retention_preview_days: int | None = None
```

`infrastructure.homeassistant` exports immutable `MaintenanceStatus` and
`HomeAssistantMaintenanceStatusPublisher`. The publisher retains the standard
injected state-client, version and optional sensor-entity constructor form and
exports `publish(status: MaintenanceStatus) -> None`.

Invalid public argument types raise `TypeError`; invalid values raise
`ValueError`. The publisher validates the complete value before its first
Home Assistant side effect.

## Error Behavior

Retention planning uses the existing persistence boundary. `StateStoreError`
propagates and follows the existing storage-warning and process exit behavior.
A Home Assistant publication failure is non-fatal, is written to the error
stream and contributes to the existing status-error cycle count.

No warning maintenance state is synthesized when persistence fails because a
failed plan contains no trustworthy counts. The existing
`sensor.price_watch_storage` warning remains the persistence-health signal.

## Dependency Direction

```text
applications.homeassistant
    +--> core.state ObservationRetentionManager
    +--> infrastructure.persistence.sqlite planner
    +--> infrastructure.homeassistant publisher

infrastructure.homeassistant --> core.state immutable plan
infrastructure.persistence.sqlite --> core.state
```

Core, Domain, Provider SDK and Rule Engine remain unchanged and deterministic.

## Consequences

The operator can assess retention impact directly in Home Assistant while
all destructive behavior remains confined to the explicit CLI command. The
preview adds one read-only database pass and one state update per enabled
catalog cycle. Large histories may make planning increasingly expensive, so
the feature is opt-in and no default retention period is introduced.
