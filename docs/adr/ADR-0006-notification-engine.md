# ADR-0006: Notification Generation and Delivery

## Status

Accepted

---

## Context

The Rule Engine determines whether a rule matched and returns an immutable
`EvaluationResult`.

The platform must convert matching results into immutable `Notification`
domain objects and deliver them through replaceable channels.

The existing architecture requires deterministic Core behavior and assigns
all side effects to Infrastructure. Notification generation and notification
delivery must therefore be separate responsibilities.

ADR-0005 previously described the Notification Engine as delivering
notifications. That wording combined pure generation with side-effecting
delivery and is clarified by this decision.

---

## Decision

Notification generation belongs to `core.notifications`.

Delivery abstractions belong to `core.notifications`; concrete delivery
implementations belong to Infrastructure.

Applications compose generation and delivery.

---

## NotificationEngine

`NotificationEngine` is deterministic, stateless and free of side effects.

Its public method is:

```python
generate(
    product: Product,
    evaluation: EvaluationResult,
    notification_id: UUID,
) -> Notification | None
```

If `evaluation.matched` is `False`, the method returns `None`.

If `evaluation.matched` is `True`, the generated `Notification` uses:

- `notification_id` as `Notification.id`
- `product.id` as `Notification.product_id`
- a deterministic product summary headed by `evaluation.reason` as
  `Notification.message`, according to ADR-0013
- `evaluation.timestamp` as `Notification.created_at`

The caller supplies the identifier. Core does not generate UUIDs.

The evaluation timestamp is reused as the notification creation timestamp.
Core does not read the system clock.

Invalid public argument types raise `TypeError`.

---

## NotificationChannel

`NotificationChannel` is a `typing.Protocol` defined in `core.notifications`.

Its public method is:

```python
send(notification: Notification) -> None
```

The Protocol defines the delivery boundary only. Core does not invoke a
channel and performs no delivery side effects.

---

## Console Delivery

The reference delivery implementation is:

```text
infrastructure.notifications.console.ConsoleNotificationChannel
```

The output stream is injected explicitly. The implementation has no hidden
dependency on global standard output.

Each notification is written using the message unchanged. ADR-0013 enriches
that deterministic message with product details, so one notification may span
multiple text lines. The Console channel prefix remains:

```text
{created_at.isoformat()} {product_id.value} {message}\n
```

The stream is flushed after the line is written.

---

## Error Handling

`NotificationError` is the base exception for notification delivery failures.

Concrete channels raise `NotificationError` for operational delivery
failures.

Invalid public argument types raise `TypeError`; they are not wrapped in
`NotificationError`.

---

## Dependency Direction

```text
Applications
    |
    +--> Infrastructure notification channels
    |
    +--> Core NotificationEngine
              |
              +--> Rule Engine API
              |
              +--> Domain
```

`core.notifications` must not import Infrastructure or Applications.

Infrastructure channels may depend on the Core notification contract and
domain `Notification` object.

---

## Alternatives Considered

### NotificationEngine delivers directly

Rejected because it would make Core invoke side effects and combine generation
with delivery orchestration.

### Console-only notification service

Rejected because business behavior would depend on one delivery technology and
new channels would require changing existing logic.

### Notification generates its own UUID and timestamp

Rejected because system time and randomness would make Core nondeterministic.

---

## Consequences

Advantages:

- deterministic and independently testable generation
- replaceable delivery channels
- explicit application composition
- no Infrastructure dependency in Core
- stable domain message passed across boundaries

Costs:

- separate generation and delivery objects
- application workflow must coordinate both steps

The separation is intentional and preserves the existing Clean Architecture
boundaries.
