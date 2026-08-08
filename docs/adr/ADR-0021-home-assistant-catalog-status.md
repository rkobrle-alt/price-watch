# ADR-0021: Home Assistant Catalog Status

## Status

Accepted

## Context

Catalog mode retains thousands of discovered references and durable product
observations, while ADR-0015 exposes only the products refreshed in the current
cycle. An operator cannot see overall catalog coverage, qualifying discounts or
the last durable discovery and refresh times from Home Assistant.

The summary must not create one mandatory dashboard card per catalog product or
move monitoring business rules into Home Assistant-specific code.

## Decision

Catalog mode publishes one aggregate state representation:

```text
sensor.price_watch_catalog
```

Core adds a provider-neutral immutable `CatalogStatistics` value and
`CatalogStatisticsReader` Protocol. SQLite implements the reader from retained
catalog data. Applications combine those statistics with latest persisted
snapshots and use the existing deterministic daily-discount engine to determine
the qualifying product count. Infrastructure formats and publishes the Home
Assistant representation.

Explicit-URL mode and the existing `sensor.price_watch_status` and product
state contracts remain unchanged.

## Core Public API

`core.catalog` exports:

```python
@dataclass(frozen=True, slots=True)
class CatalogStatistics:
    reference_count: int
    last_discovered_at: datetime | None
    last_refresh_attempt_at: datetime | None

class CatalogStatisticsReader(Protocol):
    def catalog_statistics(self, provider_id: ProviderId) -> CatalogStatistics: ...
```

Counts reject `bool`, must be non-negative and timestamps must be timezone-aware.
Invalid public argument types raise `TypeError`; invalid values raise
`ValueError`. Persistence failures raise `CatalogStoreError`.

The SQLite result uses the retained reference count, greatest `last_seen_at`
and greatest non-null `last_refresh_attempt_at` for the requested provider.

## Aggregate Entity Contract

`infrastructure.homeassistant` exports immutable `CatalogStatus` and
`HomeAssistantCatalogStatusPublisher`.

`CatalogStatus` contains:

- cycle timestamp
- catalog reference count
- observed product count
- available product count
- qualifying discount count
- configured minimum discount percentage
- last successful discovery timestamp, when known
- last refresh-attempt timestamp, when known
- provider and catalog error counts for the current cycle

The entity state is `ok` when both error counts are zero and `degraded`
otherwise. Attributes use exact strings for `Decimal`-backed percentage values
and ISO 8601 timestamps. They include `friendly_name` and the application
version.

The publisher validates the complete value before calling the injected
`HomeAssistantStateClient`.

## Application Behavior

After a completed catalog synchronization, `applications.homeassistant`:

1. reads durable catalog statistics and latest product snapshots;
2. filters snapshots to the catalog provider;
3. uses `DailyDiscountDigestEngine` with the configured threshold to count
   currently available qualifying discounts;
4. publishes the aggregate catalog state after the existing cycle status;
5. continues with daily-digest orchestration.

A `HomeAssistantError` from either status publication remains non-fatal and is
counted once as a status-error cycle. Catalog persistence failures retain their
existing fatal boundary. No clock, database or Home Assistant access enters
Core.

## Dependency Direction

```text
applications.homeassistant
    +--> core.catalog statistics contract
    +--> core.state latest snapshots
    +--> core.notifications discount engine
    +--> infrastructure.homeassistant publisher

infrastructure.persistence.sqlite
    +--> core.catalog

infrastructure.homeassistant
    +--> Home Assistant state client
```

## Alternatives Considered

Extending only the process log was rejected because it does not expose durable
operational state in Home Assistant. Publishing every catalog product as a
required dashboard card was rejected because it does not provide a concise
health view. Computing discount eligibility in the Home Assistant publisher was
rejected because it would duplicate Core business logic.

## Consequences

The operator gains one concise catalog-health entity with restart-safe timing
and aggregate coverage. The design adds one read-only Core contract and one
SQLite query but no schema migration, new credential, port or external
dependency.
