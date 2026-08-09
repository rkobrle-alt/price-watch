# STORY-023: Observation Storage Diagnostics

## Objective

Implement ADR-0024 and release v0.23.0 with non-destructive SQLite observation
diagnostics in Home Assistant.

## Scope

- add the immutable Core statistics value and reader Protocol;
- implement efficient statistics in `SqliteStateStore`;
- add storage status value and Home Assistant publisher;
- compose healthy and warning publication only in catalog mode;
- document Supervisor-managed backup and restore expectations;
- update release metadata to 0.23.0.

Do not delete, compact, vacuum or rewrite observations. Do not change SQLite
schema version 4, retention behavior, Domain, Provider SDK, Rule Engine,
notification content, CLI or explicit Home Assistant mode.

## Files

Create:

```text
core/state/statistics.py
infrastructure/homeassistant/storage_status.py
tests/unit/state/test_observation_statistics.py
tests/unit/homeassistant/test_storage_status.py
```

Modify public exports, SQLite state store, Home Assistant composition/cycle
and process error mapping, tests, operator documentation and version metadata.

## Public API

`core.state` exports `ObservationStatistics` and
`ObservationStatisticsReader` exactly as ADR-0024 defines.

`infrastructure.homeassistant` exports:

```python
@dataclass(frozen=True, slots=True)
class StorageStatus:
    timestamp: datetime
    statistics: ObservationStatistics | None

class HomeAssistantStorageStatusPublisher:
    def __init__(
        self,
        client: HomeAssistantStateClient,
        version: str,
        entity_id: str = "sensor.price_watch_storage",
    ) -> None: ...

    def publish(self, status: StorageStatus) -> None: ...
```

Every public object is documented and typed. Invalid public types raise
`TypeError`; invalid values raise `ValueError` before side effects.

## Processing and Errors

The SQLite statistics operation opens the shared version-4 database through
the existing lifecycle, issues aggregate/count/page queries, decodes at most
two snapshots and always closes the connection. It reports all operational or
persisted-data failures as `StateStoreError` with chaining.

Healthy storage publication follows completed catalog-status publication and
precedes daily-digest execution. Its Home Assistant failure is non-fatal.

The catalog-cycle wrapper attempts warning publication for the four persistence
exception types named by ADR-0024. It then re-raises the identical original
exception. Warning publication never reads the failed database, and its own
Home Assistant failure is written once without replacing the persistence
failure.

## Tests

Cover:

- statistics immutability, Protocol shape, validation and public exports;
- empty, single and multiple-product SQLite statistics;
- insertion-order boundary timestamps including out-of-order timestamps;
- allocated byte calculation and exact no-schema-migration behavior;
- malformed boundary snapshots, query/open/close failures and chaining;
- exact healthy and warning Home Assistant payloads;
- publisher construction, type/value validation and side-effect ordering;
- catalog-only composition with the shared SQLite reader;
- healthy publication order and non-fatal Home Assistant failure;
- warning attempts for every approved persistence exception;
- preservation of the original failure when warning delivery also fails;
- absence of the entity in explicit mode;
- packaging, documentation and version consistency.

Tests use temporary SQLite databases and fakes. They perform no network access
and never delete retained observations.

## Acceptance Criteria

- `sensor.price_watch_storage` reports `ok` with exact observation, product,
  timestamp and byte diagnostics after a completed catalog cycle;
- an approved catalog persistence failure attempts a `warning` state and then
  retains its original fatal error boundary;
- explicit mode and CLI behavior remain unchanged;
- schema version remains 4 and every existing row is preserved;
- no automatic retention, compaction, vacuum or backup side effect exists;
- all public APIs are exported and documented;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- all tests pass with 100 percent statement and branch coverage.
