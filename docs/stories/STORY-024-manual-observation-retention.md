# STORY-024: Manual Observation Retention

## Objective

Implement ADR-0025 and release v0.24.0 with previewable, backup-protected and
manually invoked SQLite observation retention.

## Scope

- add immutable Core retention plan/result values and manager Protocol;
- implement exact SQLite planning, backup and transactional deletion;
- preserve recent observations, every product's latest state and every
  product/currency historical-high current price;
- add the CLI `maintenance` command with plan-by-default behavior;
- expose SQLite reclaimable bytes through existing storage diagnostics;
- update documentation and release metadata to 0.24.0.

Do not schedule retention, add a Home Assistant deletion option, run retention
during deployment, vacuum automatically, change schema version 4, or modify
Domain, Provider SDK, Rule Engine, notification content or workflow ordering.

## Files

Create:

```text
core/state/retention.py
infrastructure/persistence/sqlite/retention.py
tests/unit/state/test_observation_retention.py
tests/unit/persistence/test_sqlite_observation_retention.py
```

Modify Core and Infrastructure exports, CLI arguments/parser/main, storage
statistics and publisher, tests, architecture/operator documentation and
version metadata.

## Public API

`core.state` exports `ObservationRetentionPlan`, `ObservationRetentionResult`
and `ObservationRetentionManager` exactly as ADR-0025 defines.

`infrastructure.persistence.sqlite` exports:

```python
class SqliteObservationRetentionManager:
    def __init__(self, path: Path, timeout_seconds: int = 5) -> None: ...
    def plan(self, cutoff: datetime) -> ObservationRetentionPlan: ...
    def apply(
        self,
        cutoff: datetime,
        backup_file: Path,
    ) -> ObservationRetentionResult: ...
```

The CLI adds immutable internal `MaintenanceArguments` and the public command
surface from ADR-0025. Existing exported CLI API signatures remain unchanged.

`ObservationStatistics` adds
`reclaimable_size_bytes: int = 0`. Existing positional construction remains
compatible. The Home Assistant storage entity adds the exact same attribute,
or null in warning state.

## Processing and Errors

The retention adapter decodes each observation through the existing snapshot
codec. It selects retained insertion sequences using exact `Decimal`, currency,
timestamp and product identity values. Equal maximum prices preserve their
earliest inserted occurrence.

Planning closes its connection without side effects. Apply validates the
source and destination paths before opening the database, starts an immediate
transaction, recomputes the selection, serializes the complete pre-deletion
database to a newly created backup, deletes removable sequences and commits.
It never touches other tables.

Invalid public types raise `TypeError`; naive cutoffs and equal source/backup
paths raise `ValueError`. SQLite, persisted-data, filesystem, serialization and
close failures raise `StateStoreError`. Database mutation rolls back on delete
or commit failure. A successfully written backup may remain after a later
rollback and is never silently overwritten.

## Tests

Cover:

- immutable values, Protocol shape, validation and public exports;
- empty and all-recent plans;
- cutoff boundary inclusion and out-of-order timestamps;
- latest-state protection per product;
- exact historical-high protection per product and currency;
- earliest equal-high selection;
- successful backup round-trip before deletion;
- absence of changes during planning;
- rejection of existing, equal and invalid backup paths;
- malformed snapshots and open/query/serialize/write/delete/commit/close
  failures with chaining and rollback behavior;
- repeated planning/apply outcomes and unaffected non-observation tables;
- reclaimable-byte calculation and Home Assistant representation;
- CLI parsing, plan output, explicit apply requirements, exit codes and
  unchanged existing commands;
- packaging, documentation and version consistency.

Tests use temporary databases and injected clocks. They perform no network
access and never mutate the deployed Home Assistant database.

## Acceptance Criteria

- `maintenance` without `--apply` reports a deterministic plan and creates no
  file or database change;
- apply cannot start without a distinct, non-existing backup destination;
- the backup contains the complete pre-retention database;
- removal preserves recent rows, the last inserted row per product and the
  historical-high row per product/currency;
- catalog and reservation tables remain byte-for-value logically unchanged;
- normal CLI synchronization and Home Assistant cycles never invoke retention;
- schema version remains 4 and no automatic vacuum occurs;
- reclaimable allocated bytes are visible after logical deletion;
- all public APIs are exported, typed and documented;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- all tests pass with 100 percent statement and branch coverage.
