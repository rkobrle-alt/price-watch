# STORY-012: Home Assistant Notification Delivery

## Goal

Implement deterministic rich notification content and an Infrastructure
notification channel that delegates delivery to an existing Home Assistant
notify entity according to ADR-0013.

---

## Scope

This story includes:

- richer channel-neutral `Notification.message` generation
- a structural Home Assistant service client contract
- a standard-library REST client implementation
- `HomeAssistantNotificationChannel`
- unit and boundary integration tests

This story does not include:

- Home Assistant App packaging
- reading `SUPERVISOR_TOKEN`
- changing TOML schema version 1
- CLI selection of notification channels
- direct SMTP delivery
- retries, summaries, entities or dashboards

---

## Package Structure

Create:

```text
infrastructure/homeassistant/
    __init__.py
    client.py
    exceptions.py
    urllib_client.py

infrastructure/notifications/homeassistant/
    __init__.py
    channel.py

tests/unit/homeassistant/
    __init__.py
    test_client.py
    test_notification_channel.py
    test_public_api.py

tests/integration/test_homeassistant_notification.py
```

Modify `core.notifications.NotificationEngine` and its tests for the approved
message contract. Update project metadata to version `0.12.0` only in the
release commit.

---

## Public API

Export through `infrastructure.homeassistant`:

- `HomeAssistantClient`
- `HomeAssistantError`
- `UrllibHomeAssistantClient`

Export through `infrastructure.notifications.homeassistant`:

- `HomeAssistantNotificationChannel`

Signatures must exactly match ADR-0013. Every public object has explicit typing
and documentation.

No existing package export list or public signature changes.

---

## Rich Notification Message

For a matching evaluation, `NotificationEngine.generate()` sets
`Notification.message` exactly to:

```text
{reason}\n
Product: {name}\n
Current price: {amount} {currency}\n
Availability: {available|unavailable}\n
URL: {url}
```

Requirements:

- use `Decimal` string formatting directly from `Money.amount`
- use the public `Currency.value`
- availability uses lowercase English `available` or `unavailable`
- preserve the product name and URL exactly
- do not read time, generate identifiers or localize in Infrastructure
- non-matching evaluations still return `None`
- argument validation and equality determinism remain unchanged

The immutable Domain `Notification` structure is not modified.

---

## Home Assistant Client Contract

`HomeAssistantClient` is a runtime-checkable Protocol with:

```python
call_service(
    domain: str,
    service: str,
    data: Mapping[str, object],
) -> None
```

The Protocol performs no implementation work.

---

## Standard-Library Client

`UrllibHomeAssistantClient` validates construction without network access:

- `base_url` must be a non-blank string with `http` or `https` scheme and a
  non-empty network location
- trailing slashes are removed for endpoint construction
- `access_token` must be a non-blank string
- timeout must be a positive `int` other than `bool`
- user agent must be a non-blank string and defaults to `PriceWatch/0.12`

`call_service()` validates:

- domain and service are non-blank lowercase identifiers containing only
  ASCII letters, digits and underscores
- data is a `Mapping` with string keys
- data must be JSON serializable

It serializes deterministic UTF-8 JSON using `ensure_ascii=False`, sorted keys
and compact separators. It creates a POST request to:

```text
{base_url}/services/{domain}/{service}
```

Headers are exactly:

- `Authorization: Bearer <access_token>`
- `Content-Type: application/json`
- `User-Agent: <user_agent>`

The injected opener defaults to `urllib.request.urlopen` and receives the
request plus the configured timeout. The response is used as a context manager
and read fully.

`HTTPError`, `URLError` and `OSError` are translated to `HomeAssistantError`
with chaining and a message that contains the service identifier but never the
token or payload. JSON serialization and unexpected errors propagate.

The constructor accepts the opener dependency for deterministic tests.

---

## Home Assistant Notification Channel

Construction validates:

- structural `HomeAssistantClient.call_service`
- `entity_id` matching `notify.[a-z0-9_]+`
- non-blank string title

`send()` requires an immutable Domain `Notification`. It calls the client once
with the exact domain, service and payload approved by ADR-0013.

A `HomeAssistantError` becomes:

```text
NotificationError("Home Assistant notification delivery failed")
```

with the client error as cause. `TypeError`, `ValueError`, interruption and
unexpected failures are not translated.

---

## Dependency Rules

- Core must not import Home Assistant or Infrastructure.
- `infrastructure.homeassistant` imports no Applications, Domain, Rule Engine,
  State Store, notification channel or provider package.
- the Home Assistant notification channel may import only Domain Notification,
  Core notification contracts and `infrastructure.homeassistant`.
- Applications synchronization and scheduler remain unchanged.
- CLI continues composing `ConsoleNotificationChannel`.
- no environment, filesystem, database, SMTP or Home Assistant package runtime
  dependency is introduced.

---

## Tests

Unit tests must cover:

- exact rich messages for available and unavailable products
- exact Decimal scale preservation
- unchanged non-match and public validation behavior
- Protocol conformance and all public exports
- every client constructor and method validation branch
- exact endpoint, HTTP method, body, headers and timeout
- response read and context closure
- HTTP and transport error translation with safe messages and chaining
- JSON serialization and unexpected failure propagation
- exact notification service call payload
- channel constructor and send validation
- channel error translation and unexpected failure propagation
- dependency direction and absence of secret, environment and SMTP behavior

The integration test uses the real `UrllibHomeAssistantClient`, real
`HomeAssistantNotificationChannel`, `NotificationEngine` and a fake opener. It
must verify the final REST request produced from a Domain Product and matched
EvaluationResult without network access.

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0013 and every earlier accepted ADR are followed.
- notification messages contain actionable product information.
- the HA channel targets any explicitly injected notify entity, including
  `notify.gmail_parkside_kobrle_fomei_com`.
- existing Home Assistant SMTP configuration can receive the service call.
- no SMTP credential or recipient configuration is duplicated.
- access tokens are injected and never persisted or exposed in errors.
- Core remains deterministic and Home Assistant independent.
- existing public signatures remain backward compatible.
- public APIs are exported through `__init__.py`.
- no TODOs, placeholders, pass statements, commented code or dead code remain.
- all tests pass with 100% statement and branch coverage.
