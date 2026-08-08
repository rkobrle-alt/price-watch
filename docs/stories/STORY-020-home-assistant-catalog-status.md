# STORY-020: Home Assistant Catalog Status

## Objective

Implement ADR-0021 and complete the v0.20.0 catalog-status milestone.

## Scope

- add the immutable Core catalog-statistics value and reader Protocol;
- implement statistics reading in `SqliteCatalogStore` without a schema change;
- add one immutable Home Assistant catalog-status representation and publisher;
- compose aggregate publication in Home Assistant catalog mode only;
- use latest persisted snapshots and the existing discount engine;
- update operator and architecture documentation;
- release version 0.20.0.

Explicit mode, Domain, Provider SDK, Rule Engine, synchronization public API,
notification semantics and persistence schema are out of scope.

## Public API

`core.catalog` exports `CatalogStatistics` and `CatalogStatisticsReader` exactly
as defined by ADR-0021.

`infrastructure.homeassistant` exports:

```python
@dataclass(frozen=True, slots=True)
class CatalogStatus:
    timestamp: datetime
    reference_count: int
    observed_product_count: int
    available_product_count: int
    qualifying_discount_count: int
    minimum_discount: Percentage | None
    last_discovered_at: datetime | None
    last_refresh_attempt_at: datetime | None
    provider_error_count: int
    catalog_error_count: int

class HomeAssistantCatalogStatusPublisher:
    def __init__(
        self,
        client: HomeAssistantStateClient,
        version: str,
        entity_id: str = "sensor.price_watch_catalog",
    ) -> None: ...

    def publish(self, status: CatalogStatus) -> None: ...
```

## Entity Attributes

The publisher emits the state and attributes specified by ADR-0021. Attribute
names are `friendly_name`, `last_checked`, `reference_count`,
`observed_product_count`, `available_product_count`,
`qualifying_discount_count`, `minimum_discount_percentage`,
`last_discovered_at`, `last_refresh_attempt_at`, `provider_error_count`,
`catalog_error_count` and `version`.

Optional timestamps are represented by `None` when unknown.
When `minimum_discount` is `None`, `minimum_discount_percentage` is also `None`
and `qualifying_discount_count` must be zero.

## Validation and Errors

- all public objects use complete type hints and docstrings;
- invalid public argument types raise `TypeError`;
- negative counts, naive timestamps, invalid entity IDs and blank version text
  raise `ValueError`;
- SQLite failures raise `CatalogStoreError`;
- Home Assistant delivery failures remain `HomeAssistantError`;
- no partial state publication occurs before argument validation.

## Tests

Unit tests cover immutable value validation and public exports, empty and
populated SQLite statistics, provider isolation and failure mapping, exact
healthy/degraded Home Assistant publications, catalog composition and cycle
publication, explicit-mode compatibility, architecture boundaries, package
version and operator documentation.

The complete suite must maintain 100% statement and branch coverage with no
skipped tests or warnings.

## Acceptance Criteria

- catalog mode publishes `sensor.price_watch_catalog` after every completed
  cycle;
- aggregate counts describe complete retained/latest durable state, not only
  the current refresh batch;
- discount qualification reuses existing Core behavior;
- fixed-amount-only catalog configurations remain valid and report no
  percentage-qualified products;
- last discovery and refresh-attempt times survive restart;
- a cycle with a catalog or provider error publishes `degraded`;
- explicit mode behavior remains unchanged;
- no database migration is introduced;
- every public API is exported through `__init__.py`;
- documentation, tests, version metadata and Home Assistant package agree on
  v0.20.0.
