# STORY-025: Home Assistant Retention Preview

## Objective

Implement ADR-0026 and release v0.25.0 with an optional, read-only Home
Assistant representation of the existing SQLite retention plan.

## Scope

- add the optional catalog-only `retention_preview_days` App option;
- compose the existing SQLite retention manager only as a planner;
- publish `sensor.price_watch_maintenance` after healthy storage statistics;
- expose exact plan counts and cutoff without deletion or backup creation;
- update operator documentation and release metadata to 0.25.0.

Do not expose retention apply, create a Home Assistant action or button,
schedule cleanup, delete data, create backups, vacuum SQLite, change schema
version 4, or modify Domain, Provider SDK, Rule Engine or CLI behavior.

## Files

Create `infrastructure/homeassistant/maintenance_status.py` and its focused
unit test. Modify Home Assistant configuration, composition, cycle execution
and public exports, their tests, architecture/operator documentation and
release metadata.

## Public API

`HomeAssistantConfig` adds
`retention_preview_days: int | None = None`.
`infrastructure.homeassistant` exports `MaintenanceStatus` and
`HomeAssistantMaintenanceStatusPublisher` exactly as ADR-0026 defines.
Existing public signatures remain compatible.

## Processing

When preview is configured, catalog composition creates one
`SqliteObservationRetentionManager` for the existing catalog database and one
maintenance publisher using the existing Home Assistant state client.

After successful catalog and storage status publication, the cycle computes
`cutoff = timestamp - timedelta(days=retention_preview_days)`, calls
`plan(cutoff)` exactly once and publishes the resulting status. Daily digest
processing remains afterward. The overall `status_published` result includes
maintenance publication success.

When preview is omitted, no retention manager or publisher is composed and no
plan query or maintenance state update occurs. Explicit URL mode rejects the
option.

## Validation and Errors

The option rejects `bool`, non-integers and non-positive values. Invalid
configuration returns the established usage exit code 2.

`MaintenanceStatus` validates a timezone-aware timestamp, positive integer
days and an `ObservationRetentionPlan`. The publisher validates its client,
version, entity ID and status before a side effect.

`StateStoreError` from planning propagates through the existing catalog
persistence boundary. `HomeAssistantError` from publication is reported as
`maintenance status error`, is non-fatal and marks current status publication
unsuccessful. The implementation never calls `apply()`.

## Tests

Cover immutable values and exports, exact sensor payload, validation before
side effects, Home Assistant failures, backward-compatible option parsing,
catalog-only validation, composition with and without preview, exact cutoff,
publication order, propagated planning failures and proof that `apply()` is
never invoked. Tests use fakes and temporary databases and never inspect or
mutate the deployed Home Assistant database.

## Acceptance Criteria

- existing installations without the option behave exactly as before;
- enabled preview publishes exact deterministic plan values;
- the Home Assistant App contains no path that invokes retention apply;
- no database row, backup file or SQLite allocation is changed by preview;
- CLI behavior and schema version 4 remain unchanged;
- all public APIs are typed, documented and exported through `__init__.py`;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- all tests pass with 100 percent statement and branch coverage.
