# STORY-021: Home Assistant Operational Overview

## Objective

Implement ADR-0022 and complete the v0.21.0 Home Assistant overview and
operational-diagnostics milestone.

## Scope

- extend the existing immutable `CatalogStatus` with individual notification
  and suppression counts using backward-compatible zero defaults;
- publish numeric discounted-product and catalog-error representations;
- publish the latest completed catalog-cycle timestamp representation;
- preserve the existing aggregate catalog health entity exactly;
- pass synchronization notification counts from the Home Assistant catalog
  application boundary;
- update operator, architecture and release documentation;
- release version 0.21.0.

Core, Domain, Provider SDK, Rule Engine, synchronization behavior, daily-digest
behavior, persistence schemas, App options, CLI and explicit-URL mode are out of
scope.

## Public API

`infrastructure.homeassistant.CatalogStatus` adds:

```python
notification_count: int = 0
suppressed_notification_count: int = 0
```

`HomeAssistantCatalogStatusPublisher` retains its public construction and
`publish()` signature.

## Entity Contract

The publisher updates these catalog-mode entities in order:

1. `sensor.price_watch_discounted_products`
2. `sensor.price_watch_catalog_errors`
3. `sensor.price_watch_last_checked`
4. `sensor.price_watch_catalog`

Numeric states use canonical integer strings. The timestamp state uses
`datetime.isoformat()`. Every representation includes `friendly_name`,
`last_checked` and `version`. Product and error representations use explicit
units and icons. The timestamp representation declares `device_class` as
`timestamp`.

The discounted-products attributes contain `reference_count`,
`observed_product_count`, `available_product_count`,
`minimum_discount_percentage`, `notification_count` and
`suppressed_notification_count`. The error attributes contain
`provider_error_count` and `catalog_error_count`. The timestamp attributes
contain the current catalog health string.

The existing health entity retains its `ok/degraded` state and ADR-0021
attributes, adding only the two notification diagnostic attributes.

## Validation and Errors

- invalid public argument types raise `TypeError`;
- counts reject `bool` and negative values;
- timestamps remain timezone-aware;
- the complete value is validated before publication;
- Home Assistant failures remain `HomeAssistantError` and keep the existing
  non-fatal application boundary;
- no rollback follows a partial Home Assistant publication.

## Tests

Unit tests cover exact publication order and payloads, healthy and degraded
states, zero defaults, invalid new counts, public exports and propagation of
Home Assistant failures. Application tests cover notification and suppression
count propagation, empty cycles, disabled percentage rules and existing error
handling. Integration tests verify the new REST state paths. Packaging,
documentation, dependency-direction and version tests remain authoritative.

The complete suite must maintain 100% statement and branch coverage without
skips or warnings.

## Acceptance Criteria

- a catalog cycle publishes all four aggregate/overview representations;
- the dashboard-ready discounted state equals the existing Core-qualified
  product count;
- error state equals the current provider plus catalog error count;
- latest-check state uses the completed cycle timestamp;
- individual delivered and suppressed notification counts are visible;
- the existing catalog health state remains backward compatible;
- explicit mode publishes none of the new catalog-only representations;
- no Core logic, database migration, option or new external dependency is
  introduced;
- documentation, tests, project metadata and App manifest agree on v0.21.0.
