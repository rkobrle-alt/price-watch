# ADR-0013: Home Assistant Notification Delivery

## Status

Accepted

---

## Context

Price Watch currently delivers generated notifications only to an injected
console stream. The target Home Assistant installation already owns a working
SMTP integration exposed as a notify entity. Duplicating SMTP configuration in
Price Watch would create another credential store, another recipient model and
two independent delivery configurations.

Home Assistant exposes notify entities through the generic
`notify.send_message` action. A future Home Assistant App can access the Core
REST API through the Supervisor proxy and an injected Supervisor token.

The current domain `Notification.message` contains only the Rule Engine reason.
That is sufficient for tests but not useful as an email because it omits the
product name, current price, availability and URL.

---

## Decision

Price Watch delegates email delivery to the existing Home Assistant notify
entity. It does not implement SMTP transport or store SMTP credentials.

The concrete delivery channel belongs to:

```text
infrastructure.notifications.homeassistant
```

It implements the existing `core.notifications.NotificationChannel` contract
without changing its signature.

Home Assistant Core service communication belongs to:

```text
infrastructure.homeassistant
```

This package contains a structural client contract, subsystem error and
standard-library HTTP implementation. The notification channel depends on the
client contract rather than performing HTTP directly.

---

## Notification Content

`NotificationEngine.generate()` retains its existing public signature and
return type. For a matching evaluation it now creates a channel-neutral message
with this exact shape:

```text
{evaluation.reason}
Product: {product.name}
Current price: {product.current_price.amount} {product.currency.value}
Availability: {available|unavailable}
URL: {product.url}
```

This is an intentional change to notification text behavior. The richer body
is useful to every delivery channel and remains deterministic Core business
output. The immutable `Notification` entity and its fields are unchanged.

The Console channel writes the richer message unchanged. Existing callers that
construct `Notification` directly remain compatible.

---

## Home Assistant Client Public API

```python
class HomeAssistantClient(Protocol):
    def call_service(
        self,
        domain: str,
        service: str,
        data: Mapping[str, object],
    ) -> None: ...
```

```python
class HomeAssistantError(RuntimeError): ...
```

```python
UrllibHomeAssistantClient(
    base_url: str,
    access_token: str,
    timeout_seconds: int = 10,
    user_agent: str = "PriceWatch/0.12",
    opener: Callable[..., ContextManager[BinaryIO]] = urlopen,
)
```

`base_url` is the Home Assistant REST API root, for example:

```text
http://supervisor/core/api
```

The client calls:

```text
POST {base_url}/services/{domain}/{service}
```

with UTF-8 JSON, `Content-Type: application/json`, an explicit user agent and:

```text
Authorization: Bearer <access_token>
```

The client reads and closes the response but does not interpret service result
states. Home Assistant HTTP error responses and transport failures raise
`HomeAssistantError` with exception chaining.

---

## Home Assistant Notification Channel

Public construction is:

```python
HomeAssistantNotificationChannel(
    client: HomeAssistantClient,
    entity_id: str,
    title: str = "Price Watch",
)
```

`entity_id` must match the lowercase Home Assistant notify-entity form:

```text
notify.<object_id>
```

For each immutable `Notification`, the channel calls:

```python
client.call_service(
    "notify",
    "send_message",
    {
        "entity_id": entity_id,
        "title": title,
        "message": notification.message,
    },
)
```

For the installation already in use, the intended entity is configured as
`notify.gmail_parkside_kobrle_fomei_com`. The implementation never hardcodes that deployment
value.

---

## Validation and Failure Semantics

Invalid public argument types raise `TypeError`. Blank strings, unsupported
URLs, malformed service identifiers and malformed notify entity IDs raise
`ValueError`.

`UrllibHomeAssistantClient` raises `HomeAssistantError` only for operational
HTTP or transport failures. Invalid or non-JSON-serializable service data is a
caller error and is not translated.

`HomeAssistantNotificationChannel` translates `HomeAssistantError` into the
existing `NotificationError` with chaining. Unexpected programming failures
propagate unchanged.

Workflow delivery-before-persistence and at-least-once semantics from ADR-0009
remain unchanged.

---

## Security and Deployment Boundary

The access token is an explicitly injected constructor value. It is never
logged, included in errors, persisted or added to TOML schema version 1.

This milestone does not read `SUPERVISOR_TOKEN`, package a container or modify
Home Assistant. Those responsibilities belong to the planned Home Assistant
App milestone. That App will inject the Supervisor-provided token and internal
Core API URL at its outer process boundary.

---

## Dependency Direction

```text
future applications.homeassistant
    +--> infrastructure.notifications.homeassistant
    +--> infrastructure.homeassistant
    +--> applications.synchronization

infrastructure.notifications.homeassistant
    +--> core.notifications
    +--> core.domain
    +--> infrastructure.homeassistant contract

infrastructure.homeassistant
    +--> Python standard library
```

Core imports no Home Assistant package. Reusable Application workflows import
no Home Assistant implementation. The existing CLI composition remains on the
Console channel in this milestone.

---

## Alternatives Considered

### Implement SMTP directly

Rejected because Home Assistant already manages SMTP credentials, recipients
and delivery. A second implementation would increase secret exposure and
operational duplication.

### Put Home Assistant calls in `NotificationEngine`

Rejected because Core must remain deterministic and side-effect free.

### Pass `Product` directly to notification channels

Rejected because it would break the stable `NotificationChannel` contract and
make delivery channels reconstruct notification business content. Core instead
creates a self-contained message.

### Add Home Assistant fields to the Domain notification entity

Rejected because `entity_id`, action domain and service names are
Infrastructure concerns. The existing entity can carry the required neutral
message without an HA-specific Domain extension.

---

## Consequences

Advantages:

- reuse of the existing Home Assistant SMTP integration
- no SMTP credentials or recipients in Price Watch
- useful event messages for console and future channels
- unchanged Notification entity and channel signatures
- testable HTTP and delivery boundaries
- future App composition can inject Supervisor access directly

Costs:

- notification text output intentionally changes
- the channel is not executable from the current CLI composition
- successful REST acceptance does not prove downstream SMTP delivery
- retry and delivery deduplication remain outside this milestone

---

## References

- https://www.home-assistant.io/integrations/smtp/
- https://developers.home-assistant.io/docs/core/entity/notify/
- https://developers.home-assistant.io/docs/api/rest/
- https://developers.home-assistant.io/docs/apps/communication/
