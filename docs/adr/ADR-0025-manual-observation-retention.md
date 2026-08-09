# ADR-0025: Manual Observation Retention

## Status

Accepted

## Context

Catalog monitoring appends exact observations indefinitely. ADR-0024 makes
their growth measurable, but observations also supply the historical-high
reference used by ADR-0019. Arbitrary age or count deletion could therefore
change discount qualification and email behavior.

The current Home Assistant state mechanism publishes representations only; it
does not provide a stable registered command or button boundary. Retention
must not be hidden in the interval scheduler or activated by an App default.

## Decision

Add an explicit, manual SQLite observation-retention operation and expose it
through a standalone CLI command. Planning is the default. Mutation requires
an explicit apply flag and a new backup destination.

No Home Assistant monitoring cycle invokes retention. No default retention
period, scheduled cleanup, automatic compaction or database migration is
introduced.

## Retention Semantics

For a caller-supplied timezone-aware cutoff, retain:

- every observation whose snapshot timestamp is at or after the cutoff;
- the last inserted observation for every product;
- the earliest inserted observation containing the highest historical current
  price for every product and currency.

All remaining observations are removable. These guards preserve the latest
`StateStore` value, back-in-stock comparison and ADR-0019 historical-high
reference after pruning. Snapshot timestamps, rather than insertion order,
define the requested age boundary; the latest and price guards remain based on
insertion identity and exact `Decimal` values.

The operation removes exact observations only. Catalog membership, refresh
ordering, notification reservations and daily-digest reservations are never
changed.

## Core Public API

`core.state` exports:

```python
@dataclass(frozen=True, slots=True)
class ObservationRetentionPlan:
    cutoff: datetime
    observation_count: int
    removable_observation_count: int
    retained_observation_count: int
    protected_observation_count: int

@dataclass(frozen=True, slots=True)
class ObservationRetentionResult:
    plan: ObservationRetentionPlan
    backup_file: Path

class ObservationRetentionManager(Protocol):
    def plan(self, cutoff: datetime) -> ObservationRetentionPlan: ...
    def apply(
        self,
        cutoff: datetime,
        backup_file: Path,
    ) -> ObservationRetentionResult: ...
```

`protected_observation_count` counts pre-cutoff rows retained solely by the
latest-state or historical-high guards. Counts reject `bool`, are non-negative,
sum consistently and cannot report more protected rows than retained rows.
Cutoffs must be timezone-aware. Result paths must be `Path` values.

Invalid public argument types raise `TypeError`; invalid values raise
`ValueError`. Persistence, decoding, backup and SQLite failures raise
`StateStoreError` with chaining.

## SQLite Implementation

`infrastructure.persistence.sqlite` exports
`SqliteObservationRetentionManager` with the established constructor form:

```python
SqliteObservationRetentionManager(path: Path, timeout_seconds: int = 5)
```

`plan()` is read-only. It decodes exact snapshots, calculates protected
insertion sequences and returns counts without writing a backup or changing
the database.

`apply()` acquires an immediate SQLite transaction, recomputes the plan, writes
a complete serialized database backup to a destination which did not already
exist, deletes only the planned sequences and commits. The backup path must
differ from the source database. A deletion failure rolls back database
changes; an already completed backup may remain available. The operation is
idempotent for the same cutoff apart from requiring a new backup filename.

SQLite `VACUUM` is not run automatically. Freed pages remain allocated and are
reused by later observations. ADR-0024 statistics gain backward-compatible
`reclaimable_size_bytes`, calculated from SQLite freelist pages, so logical
reclamation is visible even when the file size does not shrink.

## CLI

The existing CLI adds:

```text
price-watch maintenance \
  --database-file PATH \
  --retention-days POSITIVE_INTEGER \
  [--apply --backup-file PATH]
```

Without `--apply`, the command prints one deterministic plan and performs no
mutation. `--apply` requires `--backup-file`; a backup file without `--apply`
is rejected. The cutoff is the injected timezone-aware command timestamp minus
the requested whole-day duration.

Known retention persistence failures return exit code 1. Usage errors return
2. Existing commands and configuration modes remain unchanged.

## Dependency Direction

```text
applications.cli
    +--> core.state retention contract
    +--> infrastructure.persistence.sqlite implementation

infrastructure.persistence.sqlite --> core.state
```

Core remains deterministic and performs no filesystem or database access.
Home Assistant, Domain, Provider SDK, Rule Engine and reusable workflows do
not depend on the maintenance command.

## Consequences

Advantages:

- retention is previewable, explicit and backed up before deletion;
- current state and historical-high discount semantics survive pruning;
- normal Home Assistant operation can never delete history implicitly;
- no SQLite schema migration is required.

Costs:

- operators must stop concurrent writers and invoke maintenance deliberately;
- detailed pre-cutoff history other than protected records is intentionally
  lost after apply;
- allocated file size does not shrink without a separate explicit compaction
  decision;
- Home Assistant has no native maintenance button in this milestone.
