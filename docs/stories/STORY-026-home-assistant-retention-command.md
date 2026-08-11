# STORY-026: Home Assistant Retention Command

## Objective

Implement ADR-0027 and release v0.26.0 with an explicit, stale-plan-protected
Home Assistant command for applying the configured retention preview.

## Scope

- enable Supervisor-managed App standard input;
- parse one strict JSON-lines `apply_retention` command;
- serialize commands and monitoring cycles with one lock;
- replan and compare the expected removable count before every mutation;
- create a unique persistent backup before positive deletion;
- republish the current maintenance preview after successful processing;
- document a Home Assistant script and dashboard-button action;
- update release metadata to 0.26.0.

Do not schedule retention, add an apply App option, expose a port or ingress,
request Supervisor API access, change SQLite schema version 4, vacuum SQLite,
delete catalog or reservation rows, or modify Domain, Provider SDK or Rule
Engine behavior.

## Files

Create:

```text
applications/homeassistant/maintenance_command.py
applications/homeassistant/command_listener.py
infrastructure/persistence/sqlite/retention_backup.py
tests/unit/homeassistant_app/test_maintenance_command.py
tests/unit/homeassistant_app/test_command_listener.py
tests/unit/persistence/test_retention_backup.py
```

Modify Home Assistant composition, cycle/main boundaries and exports; the
maintenance publisher; SQLite exports; App manifest and operator docs;
architecture, roadmap, EPIC, packaging tests and version metadata.

## Public API

Export `HomeAssistantMaintenanceCommand`, `MaintenanceCommandError`,
`MaintenanceCommandProcessor`, `MaintenanceCommandResult`,
`MaintenanceCommandStatus` and `parse_maintenance_command` from
`applications.homeassistant` exactly as ADR-0027 specifies.

Export `TimestampedRetentionBackupFileFactory` from
`infrastructure.persistence.sqlite`.

Extend `applications.homeassistant.run()` only with the backward-compatible
keyword-only `command_input: TextIO | None = None` dependency. Existing
positional parameters and behavior remain unchanged.

## Processing

The listener reads complete lines until EOF. Blank lines and malformed
commands are reported and ignored. It obtains one timezone-aware timestamp
from the injected clock for every valid command and invokes the processor while
holding the shared maintenance lock.

The processor replans from that timestamp and configured retention days. It:

1. returns `STALE_PLAN` if the actual removable count differs from the command;
2. returns `NO_CHANGES` for a matching zero count;
3. obtains one backup destination and calls `apply()` for a matching positive
   count;
4. returns `APPLIED` with the exact removed count and backup path.

After every accepted outcome, the listener publishes a fresh preview using the
same cutoff. Home Assistant publication failure does not change the command
result.

## Validation and Errors

The JSON object must contain exactly `command`, `confirmation` and
`expected_removable_observation_count`. Command and confirmation literals are
case-sensitive. JSON arrays, scalars, duplicate object keys, unknown keys,
`bool` counts and negative counts are invalid.

Timestamps must be timezone-aware. Backup-directory creation and retention
persistence failures raise `StateStoreError` with chaining. The listener logs
known command and persistence failures and continues reading later commands.
Unexpected programming failures are not converted to successful outcomes.

## Tests

Cover:

- frozen values, enum, public exports and complete validation;
- malformed JSON, duplicate/unknown/missing fields and exact literals;
- stale-plan and zero-plan behavior without backup/apply calls;
- successful positive apply and exact result values;
- apply and backup-factory failures with unchanged exception boundaries;
- timestamped path format, directory creation, collision and filesystem
  failures;
- command EOF, blank/invalid lines, known failure continuation and output;
- shared-lock serialization between a cycle and command;
- command-disabled behavior without preview or injected stdin;
- exact post-command maintenance publication and `apply_available` state;
- `stdin: true`, unchanged permissions, documentation and version consistency;
- complete regression suite with 100 percent statement and branch coverage.

## Acceptance Criteria

- no Home Assistant monitoring cycle applies retention automatically;
- a persistent App option cannot trigger deletion;
- a stale expected count produces no backup and no database change;
- positive apply writes a complete non-overwritten backup before deletion;
- monitoring and maintenance never overlap;
- repeated action is replanned and cannot repeat the same deletion blindly;
- schema version remains 4 and no vacuum runs;
- current retention counts are republished after every accepted command;
- all public APIs are typed, documented and exported through `__init__.py`;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- all tests pass with 100 percent statement and branch coverage.
