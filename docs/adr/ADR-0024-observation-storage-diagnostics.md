# ADR-0024: Observation Storage Diagnostics

## Status

Accepted

---

## Context

Catalog mode appends one exact observation for every successfully refreshed
product. ADR-0017 intentionally retains those observations indefinitely and
forbids an arbitrary automatic retention limit. The operator needs evidence
about actual storage growth before approving any destructive lifecycle policy.

Existing Home Assistant states expose catalog membership and observed-product
coverage, but not the total observation count, allocated SQLite size or the
first and last inserted observation times. A database failure also terminates
the App without first projecting a storage warning into Home Assistant.

---

## Decision

Add a provider-neutral, read-only observation-statistics contract to Core, an
SQLite implementation and one Home Assistant storage-health representation.
No row is deleted or rewritten, no schema migration is introduced and no
retention policy is implied.

## Core Public API

`core.state` exports:

```python
@dataclass(frozen=True, slots=True)
class ObservationStatistics:
    observation_count: int
    observed_product_count: int
    first_observation_at: datetime | None
    last_observation_at: datetime | None
    storage_size_bytes: int

class ObservationStatisticsReader(Protocol):
    def observation_statistics(self) -> ObservationStatistics: ...
```

Counts and size reject `bool`, must be non-negative integers and the observed
product count cannot exceed the observation count. An empty history requires
both timestamps to be `None`; a non-empty history requires both timestamps.
Present timestamps must be timezone-aware.

The timestamps belong to the first and last inserted observations. They do not
impose chronological ordering because ADR-0017 permits caller-supplied snapshot
timestamps to arrive out of order.

## SQLite Behavior

`SqliteStateStore` implements `ObservationStatisticsReader`. It returns:

- total rows in `observations`;
- distinct canonical product identifiers;
- decoded timestamps from the first and last rows by insertion sequence;
- allocated main-database bytes from SQLite page count multiplied by page
  size.

Only the two boundary snapshots are decoded. Existing schema validation and
exact snapshot decoding remain authoritative. SQLite, schema, close and
persisted-data failures raise `StateStoreError`. Invalid public argument types
retain their existing behavior.

The statistics query performs no mutation, compaction, vacuum, backup or
filesystem deletion.

## Home Assistant Representation

`infrastructure.homeassistant` exports immutable `StorageStatus` and
`HomeAssistantStorageStatusPublisher`.

`StorageStatus` contains a timezone-aware check timestamp and either complete
`ObservationStatistics` or `None`. The publisher updates:

```text
sensor.price_watch_storage
```

Its state is `ok` when statistics were read and `warning` when a catalog
persistence failure was reported. Attributes contain `friendly_name`,
`last_checked`, application `version` and either all five statistics or null
diagnostic values. Bytes use `storage_size_bytes`; no decimal unit conversion
is performed.

The publisher validates the complete value before its Home Assistant side
effect and translates no errors. Home Assistant failures retain the existing
`HomeAssistantError` boundary.

## Application Behavior

Home Assistant catalog composition injects the shared `SqliteStateStore` as
the statistics reader and a storage-status publisher using the existing state
client.

After a completed catalog status publication and before the daily digest, the
Application reads and publishes healthy storage statistics. A Home Assistant
publication failure is non-fatal and contributes to the existing status-error
cycle count.

If catalog execution raises `CatalogStoreError`, `StateStoreError`,
`NotificationReservationError` or `DailyDigestReservationError`, the
Application attempts one warning publication without reading SQLite and then
re-raises the original persistence exception. A warning-publication failure is
reported to the error stream but never masks the original failure.

Explicit mode and the CLI do not compose storage diagnostics.

## Dependency Direction

```text
applications.homeassistant
    +--> core.state ObservationStatisticsReader
    +--> infrastructure.homeassistant publisher

infrastructure.persistence.sqlite --> core.state
infrastructure.homeassistant --> core.state value
```

Core remains deterministic and imports neither SQLite, Home Assistant nor
Applications.

## Consequences

Advantages:

- storage growth becomes measurable before retention is considered;
- database failures can leave a visible Home Assistant warning;
- no user history is changed or destroyed;
- existing database and public workflow contracts remain compatible.

Costs:

- one aggregate query and one Home Assistant state update per catalog cycle;
- a hard process termination can still prevent warning publication;
- backup execution and retention remain future explicit decisions.
