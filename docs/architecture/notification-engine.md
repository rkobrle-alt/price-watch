# Notification Engine Architecture

## Purpose

The Notification subsystem converts matching rule evaluation results into
immutable domain notifications and delivers them through replaceable
Infrastructure channels.

Generation and delivery are separate responsibilities.

---

## Packages

```text
core/notifications/
    __init__.py
    channel.py
    engine.py
    exceptions.py
    reservation.py
    reservation_policy.py
    daily_digest.py
    digest_channel.py
    digest_reservation.py

infrastructure/notifications/
    __init__.py
    console/
        __init__.py
        channel.py
    homeassistant/
        __init__.py
        channel.py

infrastructure/homeassistant/
    __init__.py
    client.py
    exceptions.py
    urllib_client.py
```

Core contains the pure generation service and delivery abstraction.

Infrastructure contains concrete delivery channels.

Applications compose the two.

---

## Core Public API

The `core.notifications` package exports:

- `NotificationEngine`
- `NotificationChannel`
- `NotificationError`
- `NotificationReservation`
- `NotificationReservationStore`
- `NotificationReservationError`
- `PriceDropReservationPolicy`
- `DailyDiscountDigest`
- `DailyDiscountDigestEngine`
- `DailyDiscountDigestChannel`
- `DailyDigestReservationStore`
- `DailyDigestReservationError`

### NotificationEngine

Construction requires no arguments:

```python
NotificationEngine()
```

Public method:

```python
generate(
    product: Product,
    evaluation: EvaluationResult,
    notification_id: UUID,
) -> Notification | None
```

The method returns `None` for a non-matching evaluation.

For a matching evaluation it creates a `Notification` from the supplied
product, evaluation result and identifier. According to ADR-0013, its
channel-neutral message contains the reason, product name, current price,
availability and URL. When a reference price exists, the message also contains
its exact amount and exact discount percentage according to ADR-0019.

The engine never reads time, generates identifiers or performs I/O.

### NotificationChannel

```python
send(notification: Notification) -> None
```

`NotificationChannel` is a Protocol. It contains no implementation.

### NotificationError

`NotificationError` represents operational delivery failures reported by
concrete notification channels.

Invalid argument types use `TypeError`.

### Price alert reservations

`NotificationReservation` identifies one logical price alert by product, rule
type, currency and current price. `NotificationReservationStore` is a Protocol
for atomic reservation and idempotent release. `PriceDropReservationPolicy`
deterministically creates identities only for matching price-drop evaluations.
Core does not persist reservations.

### Daily discount digest

`DailyDiscountDigestEngine` deterministically selects available products with
an approved reference and sufficient discount from caller-supplied latest
snapshots. It creates one immutable, channel-neutral daily message, including
an explicit empty state. `DailyDiscountDigestChannel` and
`DailyDigestReservationStore` are Protocols; Core performs neither delivery nor
persistence.

---

## Infrastructure Public API

The `infrastructure.notifications.console` package exports:

- `ConsoleNotificationChannel`

The `infrastructure.notifications.homeassistant` package exports:

- `HomeAssistantNotificationChannel`

The `infrastructure.homeassistant` package exports:

- `HomeAssistantClient`
- `HomeAssistantError`
- `UrllibHomeAssistantClient`

The Console channel receives an explicit text output stream during
construction.

It writes and flushes one deterministic line per notification:

```text
{created_at.isoformat()} {product_id.value} {message}\n
```

The Home Assistant channel delegates the same immutable message to an injected
Home Assistant service client using `notify.send_message`. It targets an
explicit notify entity and translates Home Assistant operational failures to
`NotificationError`. SMTP configuration and credentials remain owned by Home
Assistant.

ADR-0014 composes this channel in `applications.homeassistant`. The process
boundary injects Supervisor API access; notification generation and delivery
contracts remain unchanged.

---

## Application Composition

Applications perform the sequence:

```text
EvaluationResult
    |
    v
optional durable price reservation
    |
    +--> existing reservation: suppress
    |
    v
NotificationEngine.generate
    |
    +--> None: no delivery
    |
    +--> Notification
             |
             v
       NotificationChannel.send
```

The generation stage is always invoked. A non-match produces no domain
notification and therefore no delivery call.

---

## Dependency Rules

`core.notifications` may depend on:

- Domain
- the Rule Engine public API
- the Python standard library

It must not depend on:

- Infrastructure
- Applications
- HTTP libraries
- databases
- Home Assistant
- filesystem or environment configuration

Infrastructure notification channels may depend on Core contracts and domain
objects.

---

## Determinism

All identifiers and timestamps enter through public method arguments or
immutable input objects.

Repeated generation with equal inputs produces an equal `Notification`.
