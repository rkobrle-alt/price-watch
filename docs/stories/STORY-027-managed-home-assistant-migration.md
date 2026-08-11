# STORY-027: Managed Home Assistant Distribution and State Migration

## Objective

Implement ADR-0028 and release v0.27.0 so Price Watch can be installed and
updated from its Home Assistant repository without discarding the state of the
existing `local_price_watch` installation.

## Scope

- expose the repository installation path in project and App documentation;
- add the writable Home Assistant `share` mapping required by migration;
- add a strict, serialized `export_migration` stdin command;
- create a versioned, checksummed ZIP from exactly one active state artifact
  and canonical active options;
- add an explicit checksum-protected first-start import configuration;
- import and verify state before the first monitoring cycle;
- make repeated import of the same completed bundle idempotent;
- document backup, hand-off, verification and rollback;
- update release metadata to 0.27.0.

Do not modify Core, Domain, Provider SDK, Rule Engine, SQLite schema version 4,
catalog semantics, notification rules, digest timing, retention behavior or
existing sensor entity IDs. Do not overwrite Supervisor-owned `options.json`,
infer consent from a file's presence, expose a port or ingress, or access any
path outside the fixed migration directory.

## Files

Create:

```text
applications/homeassistant/migration.py
infrastructure/persistence/migration/__init__.py
infrastructure/persistence/migration/_format.py
infrastructure/persistence/migration/_state.py
infrastructure/persistence/migration/archive.py
infrastructure/persistence/migration/model.py
tests/unit/homeassistant_app/test_migration.py
tests/unit/persistence/test_migration_archive.py
```

Modify the Home Assistant configuration, command listener, process boundary
and public exports; App manifest and operator docs; architecture, roadmap,
EPIC, packaging tests and version metadata.

## Public API

`applications.homeassistant` exports:

```python
@dataclass(frozen=True, slots=True)
class HomeAssistantMigrationImport:
    archive_file: str
    archive_sha256: str

@dataclass(frozen=True, slots=True)
class HomeAssistantMigrationExportCommand: ...

parse_migration_export_command(line: str) -> HomeAssistantMigrationExportCommand
```

`HomeAssistantConfig` gains:

```python
migration_import: HomeAssistantMigrationImport | None = None
```

`infrastructure.persistence.migration` exports:

```python
class MigrationArchiveError(RuntimeError): ...

@dataclass(frozen=True, slots=True)
class MigrationExportResult:
    archive_file: Path
    archive_sha256: str
    state_file_name: str

class ZipMigrationArchive:
    def export(
        self,
        data_directory: Path,
        options: Mapping[str, object],
        timestamp: datetime,
        application_version: str,
    ) -> MigrationExportResult: ...

    def import_state(
        self,
        archive_file: str,
        archive_sha256: str,
        data_directory: Path,
        options: Mapping[str, object],
    ) -> None: ...
```

All public objects are typed, documented and exported through `__init__.py`.

## Configuration

The optional App fields are:

```text
migration_import_file: string basename
migration_import_sha256: lowercase SHA-256
migration_import_confirmation: IMPORT_MIGRATION
```

All three must be absent or valid together. They are converted into one
immutable `HomeAssistantMigrationImport`; the exact confirmation is not
retained in runtime configuration. Existing option documents produce `None`.

## Export Behavior

The command object contains no values. Its parser accepts exactly `command`
and `confirmation`, rejects duplicate or unknown fields, and reuses the
existing JSON-lines error boundary.

The existing listener routes `apply_retention` unchanged and routes
`export_migration` while holding the shared operation lock. Export remains
available independently of retention preview. A successful log line contains
the bundle path and SHA-256. Known migration failures are logged and later
commands continue.

The archive adapter accepts exactly one of `/data/catalog.sqlite3` and
`/data/state.json`. Catalog export uses an online SQLite backup followed by
an integrity check. Explicit state is decoded as JSON before inclusion.
Options are canonical UTF-8 JSON and exclude only import-only fields.

The ZIP has fixed allowed member names and a version-1 manifest containing
application version, timezone-aware creation time, state filename and exact
payload digests and sizes. The archive and temporary files are created without
overwriting existing paths and finalized atomically.

## Import Behavior

Import executes after options validation but before `_compose_homeassistant`.
The archive basename resolves only inside the fixed migration directory. The
source must be a regular non-symbolic file. The complete supplied SHA-256 and
all manifest metadata are verified before any destination write.

The current options, after removing the three import-only fields, must equal
the exported canonical options. The state payload is validated in a temporary
file. An unrelated existing `catalog.sqlite3` or `state.json` rejects import.
The valid file is atomically installed under its original fixed name and a
versioned import marker is written.

If the marker and installed state match the requested bundle, later restarts
skip import. If installation completed but marker creation was interrupted, a
matching installed state permits marker recovery. Any different existing state
or requested bundle is rejected.

## Validation and Errors

Public invalid types raise `TypeError`. Blank values, non-basenames, invalid
confirmation, malformed SHA-256, naïve timestamps, unsupported manifests,
unexpected ZIP members, duplicate ZIP names, excessive payload sizes,
checksum/size mismatch, invalid JSON, failed SQLite integrity, option mismatch
and conflicting destination state raise their documented configuration or
`MigrationArchiveError` boundary.

No failure removes or changes the source bundle. No failure overwrites an
unrelated state file. Temporary files are removed when practical.

## Tests

Add tests for:

- optional configuration compatibility and all-or-none import fields;
- strict command parsing, duplicate keys and exact literals;
- catalog SQLite online export and explicit JSON export;
- refusal of missing, zero or multiple state artifacts;
- canonical option filtering and equality;
- archive/member checksums, sizes, names and schema validation;
- traversal, absolute path, symbolic source and overwrite rejection;
- SQLite integrity and JSON decoding failures;
- import before composition and before the first cycle;
- idempotent restart and interrupted-marker recovery;
- conflicting existing state and mismatched bundle rejection;
- shared-lock command serialization and known-error continuation;
- repository metadata, writable share mapping, documentation and version
  consistency;
- complete regression suite at 100 percent statement and branch coverage.

## Acceptance Criteria

- the repository is discoverable from its root `repository.yaml` and recursive
  App manifest;
- existing installations without migration fields behave unchanged;
- export is explicit, read-only with respect to `/data` and serialized with
  monitoring;
- the bundle contains the exact active database state and canonical options;
- import cannot begin without explicit confirmation and the complete archive
  checksum;
- no monitoring cycle runs before a requested import succeeds;
- existing unrelated state is never overwritten;
- catalog history and all SQLite reservations survive the hand-off;
- the old local installation can be restarted unchanged for rollback;
- all public APIs are typed, documented and exported through `__init__.py`;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- all tests pass with 100 percent statement and branch coverage.
