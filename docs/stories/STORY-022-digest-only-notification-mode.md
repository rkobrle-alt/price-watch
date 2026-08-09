# STORY-022: Digest-Only Catalog Notification Mode

## Objective

Implement ADR-0023 so Home Assistant catalog monitoring can deliver one daily
discount summary without individual product emails.

## Scope

- add strict parsing and immutable configuration for
  `individual_notifications_enabled`;
- preserve omission as `true` for existing option documents;
- set the packaged default to `false` for new installations;
- supply no individual synchronization rules in disabled catalog mode;
- preserve daily digest selection, delivery, catalog monitoring and status;
- update operator and release documentation;
- release version 0.22.0.

Core, Domain, Provider SDK, Rule Engine, notification contracts,
synchronization APIs, persistence schemas, CLI and explicit Home Assistant
mode behavior are out of scope.

## Public API

`applications.homeassistant.HomeAssistantConfig` adds:

```python
individual_notifications_enabled: bool = True
```

`parse_homeassistant_options()` accepts the optional catalog-only boolean
`individual_notifications_enabled` and otherwise retains its public
signature.

## Behavior

- omitted option: individual catalog alerts remain enabled;
- explicit `true`: existing price-drop and back-in-stock rules are composed;
- explicit `false`: catalog composition exposes an empty individual rule
  tuple;
- the daily digest remains independently controlled by
  `daily_digest_enabled`;
- the packaged App options select `false`, `daily_digest_enabled: true` and
  the existing `08:00` Europe/Prague delivery time.

The disabled mode continues to fetch and persist products, compute references,
publish all catalog status states and run the daily digest. Individual
notification and suppression counts are zero because there are no individual
evaluations.

## Validation and Compatibility

- invalid option and direct-construction types raise `TypeError` or the
  established wrapped `ConfigurationError` at the parser boundary;
- `individual_notifications_enabled` is rejected in explicit mode;
- a false direct configuration without catalog monitoring raises `ValueError`;
- existing catalog option documents that omit the option behave unchanged;
- existing explicit option documents, CLI and persisted SQLite data behave
  unchanged.

## Tests

Tests cover:

- omitted, true, false and invalid option values;
- strict rejection in explicit mode;
- direct immutable configuration validation;
- catalog composition with existing rules enabled and an empty tuple when
  disabled;
- continued daily-digest composition in disabled mode;
- a catalog integration cycle proving zero individual notify calls before the
  single daily digest call;
- exact App manifest default and schema;
- version and documentation consistency.

The complete suite must maintain 100 percent statement and branch coverage
without skips or warnings.

## Acceptance Criteria

- one enabled daily digest can contain all current qualifying products and
  their URLs;
- no individual product email is sent when
  `individual_notifications_enabled` is false;
- catalog discovery, refresh, history, discount qualification and Home
  Assistant status publication continue;
- at most one digest is sent per Europe/Prague calendar date;
- omission preserves existing individual-alert behavior;
- packaged defaults select digest-only email behavior;
- no Core, Infrastructure or persistence API changes;
- all public APIs remain exported and documented;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- all tests pass with 100 percent statement and branch coverage.
