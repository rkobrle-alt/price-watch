# ADR-0028: Managed Home Assistant Distribution and State Migration

## Status

Accepted

## Context

Price Watch is currently installed as the local Home Assistant App
`local_price_watch`. Releases are published as multi-architecture GHCR images,
but each update still requires a manual copy into `/addons`, a store reload and
an explicit App update.

Home Assistant derives an App identity from both its repository and manifest
slug. A local installation uses the `local` repository identifier while an App
installed from a GitHub repository uses a hash derived from that repository.
Adding the GitHub repository therefore creates a second App identity rather
than adopting `local_price_watch`. The two identities have different
Supervisor-managed `/data` directories and standard-input action targets.

The catalog database contains product membership, exact price and availability
history, refresh ordering, individual-alert reservations and daily-digest
reservations. Starting the repository App with empty state would lose this
operational continuity and could repeat notifications.

## Decision

Version 0.27.0 makes the existing GitHub repository the supported installation
and update source for new deployments. The existing recursive App location
`homeassistant/price_watch` and root `repository.yaml` remain authoritative.
The manifest continues to reference the published multi-architecture GHCR
image.

Migration from `local_price_watch` is an explicit two-installation hand-off:

1. the running local App exports one validated state bundle to the shared
   `/share/price-watch-migration` directory;
2. the local App is stopped but retained as the rollback installation;
3. the repository App is installed and configured with the exported settings;
4. on its first start, the repository App validates and imports the bundle
   before composing or running the first monitoring cycle;
5. only after successful operational verification may the local App be
   removed.

No implementation renames, moves or directly edits Supervisor-owned App data.
A Home Assistant backup remains mandatory before the hand-off but is not
treated as a supported cross-identity data transformer.

## Shared Migration Boundary

The App manifest adds a writable `share` mapping. Migration files are confined
to:

```text
/share/price-watch-migration
```

The mapping is used only for explicit migration export and import. Core,
Domain, Provider SDK, Rule Engine and normal persistence paths remain
unchanged.

The local App accepts this strict Supervisor-stdin command:

```json
{
  "command": "export_migration",
  "confirmation": "EXPORT_MIGRATION"
}
```

The command is serialized by the same process lock as catalog monitoring and
retention. Export determines the active state artifact from the already
validated monitoring mode in `options.json`: catalog mode selects
`catalog.sqlite3`, while explicit URL mode selects `state.json`. This permits a
read-only inactive artifact left by an earlier mode transition; it is neither
exported nor modified. The selected artifact must be a regular non-symbolic
file. Export uses the SQLite online backup API for catalog mode and an exact
validated JSON copy for explicit mode. The resulting ZIP contains:

- a versioned manifest;
- one state artifact (`catalog.sqlite3` or `state.json`);
- a canonical copy of the active non-secret App options;
- SHA-256 digests for every payload.

The process log reports the final bundle path and complete archive SHA-256.
Export never changes `/data`.

## Import Contract

The packaged App schema adds three optional settings which must be supplied
together:

```text
migration_import_file
migration_import_sha256
migration_import_confirmation
```

The file value is a basename below the fixed migration directory. Paths,
directory traversal and symbolic source files are rejected. The confirmation
must equal `IMPORT_MIGRATION` and the SHA-256 must be a lowercase 64-character
hexadecimal digest.

When configured, import runs synchronously before normal composition and the
first monitoring cycle. It verifies:

- the complete archive digest;
- the manifest schema and allowed members;
- every member size and SHA-256 digest;
- the exported and currently configured options after excluding the three
  import-only settings;
- JSON state decoding or SQLite `PRAGMA integrity_check`;
- absence of an unrelated target state.

The imported state file is installed atomically. A durable marker records the
archive digest and state digest. Repeating the same configured import is an
idempotent no-op; requesting a different bundle after state exists is rejected.
The bundle's options are validation input only and never overwrite
Supervisor-owned `/data/options.json`.

After the import and first monitoring cycle have been verified, operators
remove all three `migration_import_*` settings. The imported state and durable
marker remain in the managed App's `/data` directory; ordinary subsequent
starts do not depend on the shared migration bundle.

## Public API

`applications.homeassistant` exports immutable `HomeAssistantMigrationImport`,
`HomeAssistantMigrationExportCommand` and `parse_migration_export_command`.
`HomeAssistantConfig` gains the backward-compatible optional
`migration_import` field.

`infrastructure.persistence.migration` exports `MigrationArchiveError`,
`MigrationExportResult` and `ZipMigrationArchive`.

Invalid public argument types raise `TypeError`. Invalid configuration values
raise `ConfigurationError` or `ValueError` at their existing boundaries.
Archive, filesystem, decoding, integrity and consistency failures raise
`MigrationArchiveError` with their original cause chained when applicable.

## Dependency Direction

```text
applications.homeassistant
    +--> infrastructure.persistence.migration
    +--> existing Home Assistant composition

infrastructure.persistence.migration
    +--> Python filesystem, ZIP, JSON and SQLite facilities
```

Migration is an outer operational concern. Infrastructure imports neither
Applications nor Core business services. Core remains deterministic and
independent of Home Assistant.

## Rollback

The local App is stopped, not uninstalled, during acceptance testing. Its
unchanged `/data` is the immediate rollback source. If the repository App
fails verification, it is stopped and the local App is restarted. The shared
bundle and the pre-migration Home Assistant backup provide additional recovery
artifacts.

Dashboard scripts invoking `hassio.addon_stdin` must change their `addon`
target from `local_price_watch` to the repository App's displayed slug after
migration. REST-created sensor entity IDs remain unchanged.

## Alternatives Considered

### Treat the repository App as an in-place update

Rejected because Home Assistant assigns a different repository-prefixed App
identity and persistent data directory.

### Rewrite a Home Assistant backup slug

Rejected because archive internals are Supervisor-owned and no documented
cross-identity restore contract exists.

### Start with empty history

Rejected because it discards user data and durable notification reservations.

### Automatically discover migration files

Rejected because the presence of a shared file is not operator consent to
replace application state.

## Consequences

Future releases become normal Home Assistant repository updates. Migration is
explicit, checksum-protected and happens before monitoring, while the original
installation remains available for rollback. The cost is a temporary second
App installation, a writable shared-directory permission and one deliberate
configuration hand-off.
