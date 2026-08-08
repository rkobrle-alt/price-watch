# ADR-0022: Home Assistant Operational Overview

## Status

Accepted

## Context

ADR-0021 publishes complete catalog statistics as attributes of
`sensor.price_watch_catalog`, but the entity state is intentionally limited to
`ok` or `degraded`. A dashboard tile therefore does not show how many Parkside
products currently qualify for the configured discount. Operators also need a
concise indication of current-cycle errors and the time of the latest completed
catalog check without opening developer tools.

The existing aggregate value already contains the required catalog data. The
overview must not duplicate discount business logic, add persistence, introduce
a Home Assistant integration runtime or change the established health entity.

## Decision

Catalog mode extends `HomeAssistantCatalogStatusPublisher` with three
additional read-only state representations:

```text
sensor.price_watch_discounted_products
sensor.price_watch_catalog_errors
sensor.price_watch_last_checked
```

The existing `sensor.price_watch_catalog` state and attributes remain backward
compatible. Explicit-URL mode remains unchanged.

`sensor.price_watch_discounted_products` uses the already computed qualifying
discount count as its numeric state. Its attributes provide the retained,
observed and available counts, configured minimum percentage, successful
individual notification count and suppressed individual notification count.

`sensor.price_watch_catalog_errors` uses the sum of current-cycle provider and
catalog errors as its numeric state and exposes both component counts.

`sensor.price_watch_last_checked` uses the timezone-aware completed-cycle
timestamp as its state and declares Home Assistant timestamp device class.

The publisher validates the complete immutable value before its first side
effect. It publishes the three overview representations first and the existing
catalog health state last. A final `ok` health update therefore means Home
Assistant accepted every overview representation for that cycle. Partial
publication is not rolled back; the next cycle retries the complete current
representation.

## Public API

`CatalogStatus` gains two backward-compatible fields with zero defaults:

```python
notification_count: int = 0
suppressed_notification_count: int = 0
```

They describe successfully delivered and durably suppressed individual
notifications from the completed synchronization result. Daily-digest delivery
retains its separate ADR-0020 status and is not represented as an individual
notification.

`HomeAssistantCatalogStatusPublisher` retains its existing constructor and
`publish(status)` method. No Core, Domain, Provider SDK, Rule Engine, scheduler,
notification or persistence public API changes.

## Validation and Errors

New counts reject `bool`, must be integers and cannot be negative. Invalid
arguments raise `TypeError` or `ValueError` before state publication.
`HomeAssistantError` retains the existing non-fatal catalog-status publication
boundary in the Home Assistant application.

## Dependency Direction

```text
applications.homeassistant
    +--> existing synchronization result
    +--> infrastructure.homeassistant catalog publisher

infrastructure.homeassistant
    +--> Core Domain percentage value
    +--> Home Assistant state client contract
```

Core remains deterministic and imports neither Infrastructure nor Home
Assistant.

## Alternatives Considered

Changing `sensor.price_watch_catalog` to a numeric state was rejected because
it would break automations that depend on `ok` and `degraded`. A custom Home
Assistant integration or ingress dashboard was rejected because three native
state representations satisfy the operational need without another runtime or
authentication surface. Recomputing discounts in the publisher was rejected
because ADR-0021 already requires the existing deterministic Core engine.

## Consequences

The Home dashboard can show a useful discount count, error count and completed
check time while the existing health contract remains stable. The design adds
three best-effort Home Assistant state calls per catalog cycle and no database
schema, credential, port or runtime dependency.
