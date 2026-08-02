# ADR-0015: Home Assistant Status Entities

## Status

Accepted

---

## Context

The Home Assistant App continuously monitors products and emits notifications,
but normal cycles are visible only in process logs. An operator cannot inspect
the latest product price, availability or cycle outcome from the Home Assistant
state UI.

The existing App already has narrowly scoped access to the Home Assistant Core
REST API according to ADR-0014. Home Assistant supports creating or updating a
state representation through `POST /api/states/<entity_id>`. Such a state is not
backed by a registered Home Assistant integration entity and does not control a
device.

---

## Decision

The Home Assistant App publishes read-only state representations after every
completed synchronization cycle.

The feature uses the existing Home Assistant Core API proxy and
`SUPERVISOR_TOKEN`. It introduces no ingress, exposed port, MQTT dependency,
Supervisor API permission or custom Home Assistant integration.

State publication is an Infrastructure side effect. It does not change Core,
Domain, Provider SDK, Rule Engine, State Store or synchronization contracts.

---

## State Client Contract

`infrastructure.homeassistant` exports:

```python
class HomeAssistantStateClient(Protocol):
    def set_state(
        self,
        entity_id: str,
        state: str,
        attributes: Mapping[str, object],
    ) -> None: ...
```

`UrllibHomeAssistantClient` implements this contract in addition to its
existing service-call contract. `set_state()` sends deterministic UTF-8 JSON
to:

```text
POST {base_url}/states/{entity_id}
```

The request body contains exactly `state` and `attributes`. HTTP and transport
failures raise the existing `HomeAssistantError` with exception chaining.
Invalid public argument types, including non-string attribute keys, raise
`TypeError`; malformed entity IDs and blank states raise `ValueError`.

---

## Status Publisher

`infrastructure.homeassistant` exports:

```python
HomeAssistantStatusPublisher(
    client: HomeAssistantStateClient,
    version: str,
    status_entity_id: str = "sensor.price_watch_status",
)
```

```python
publish_cycle(
    products: tuple[Product, ...],
    timestamp: datetime,
    notification_count: int,
    provider_error_count: int,
) -> None
```

The publisher validates all arguments before performing a side effect.
Timestamps must be timezone-aware. Counts must be non-negative integers and
must reject `bool`.

Product states are published first in tuple order. The cycle status is
published last so an `ok` status means every product state for that cycle was
accepted by Home Assistant.

No rollback is attempted after a partial publication failure. The next cycle
retries the complete current representation.

---

## Entity Contract

The fixed cycle entity is `sensor.price_watch_status`.

Its state is `ok` when `provider_error_count` is zero and `provider_error`
otherwise. Its attributes are:

- `friendly_name`: `Price Watch Status`
- `last_checked`: cycle timestamp in ISO 8601 format
- `product_count`
- `notification_count`
- `provider_error_count`
- `version`

Each successfully fetched product is represented by:

```text
sensor.price_watch_product_<product UUID hex>
```

The state is the exact `Decimal` price encoded as a string. It is never
converted through `float`. Product attributes are:

- `friendly_name`
- `device_class`: `monetary`
- `unit_of_measurement`: ISO currency code
- `available`: boolean availability
- `product_id`: canonical UUID string
- `url`
- `last_checked`: cycle timestamp in ISO 8601 format
- `entity_picture` only when the product has an image URL

Entity identifiers are deterministic because Lidl product identifiers are
stable according to ADR-0007. These state representations are intentionally
not entity-registry entries. They are republished by the App after every
completed cycle and after App restart.

---

## Application Behavior

`applications.homeassistant` composes one `HomeAssistantStatusPublisher` with
the same REST client used by notification delivery.

After `SynchronizationWorkflow.run()` completes, the App publishes the
successful products and cycle counts from the immutable
`SynchronizationResult`.

Status publication is operational observability, not monitoring business
logic. A `HomeAssistantError` during status publication is written to stderr,
recorded as a status-error cycle and does not stop later scheduled cycles. A
finite run returns exit code `1` when any provider or status-error cycle
occurred. Unexpected programming failures still propagate.

Existing notification delivery remains mandatory and keeps the
delivery-before-persistence semantics of ADR-0009. Notification failures still
stop execution. Status publication happens only after the workflow has
finished and therefore cannot alter evaluation, notification or persistence
results.

---

## Dependency Direction

```text
applications.homeassistant
    +--> applications.synchronization
    +--> infrastructure.homeassistant status publisher

infrastructure.homeassistant
    +--> public Core Domain Product
    +--> Python standard library HTTP
```

Infrastructure does not import Applications. Core imports neither
Infrastructure nor Home Assistant.

---

## Alternatives Considered

### Custom Home Assistant integration

Deferred because it provides registry-backed entities and richer lifecycle
management at the cost of a second deployable artifact and Home Assistant
runtime dependency. The current App requires only read-only operational
visibility.

### MQTT discovery

Rejected because it introduces broker configuration, credentials and another
delivery dependency when the App already has Core API access.

### App ingress dashboard

Rejected because it introduces an HTTP server, exposed UI and independent
authentication surface. Native Home Assistant state cards satisfy the current
visibility need.

### Manual sync and test-notification controls

Deferred. Registering stable user actions requires a separate command boundary
or Home Assistant integration contract. App restart already performs an
immediate synchronization, and SMTP delivery can be tested through the existing
notify entity without adding control logic to this story.

---

## Consequences

Advantages:

- current prices and cycle health become visible in Home Assistant
- no new credentials, ports or runtime dependencies
- exact monetary values and stable product identity
- observability failures do not disable price monitoring
- unchanged Core and reusable workflow APIs

Costs:

- REST-created states are not entity-registry-backed integration entities
- state publication is non-transactional
- Home Assistant history may record periodic status updates
- manual control remains outside this milestone

---

## References

- https://developers.home-assistant.io/docs/api/rest/
- https://developers.home-assistant.io/docs/apps/communication/
- https://developers.home-assistant.io/docs/core/entity/sensor/
