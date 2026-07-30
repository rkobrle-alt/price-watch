# STORY-005: Notification Engine

## Goal

Implement deterministic notification generation and the first Infrastructure
delivery channel according to ADR-0006.

The story must preserve the separation between pure Core generation,
Infrastructure delivery and Application composition.

---

## Package Structure

Create:

```text
core/notifications/
    __init__.py
    channel.py
    engine.py
    exceptions.py

infrastructure/notifications/
    __init__.py
    console/
        __init__.py
        channel.py

tests/unit/notifications/
    __init__.py
    helpers.py
    test_architecture.py
    test_console_channel.py
    test_notification_engine.py
    test_public_api.py
```

---

## Core Public API

Export through `core.notifications`:

- `NotificationEngine`
- `NotificationChannel`
- `NotificationError`

Every public object must have explicit type hints and a docstring.

---

## NotificationEngine

`NotificationEngine` is stateless and performs no I/O.

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

Behavior for `evaluation.matched is False`:

- return `None`
- do not create a `Notification`

Behavior for `evaluation.matched is True`:

- return an immutable domain `Notification`
- set `id` to `notification_id`
- set `product_id` to `product.id`
- set `message` to `evaluation.reason`
- set `created_at` to `evaluation.timestamp`

Invalid `product`, `evaluation` or `notification_id` argument types raise
`TypeError`.

The method must not obtain time or generate an identifier.

---

## NotificationChannel

Define `NotificationChannel` using `typing.Protocol`.

Required method:

```python
send(notification: Notification) -> None
```

The Protocol contains no delivery implementation.

---

## NotificationError

Create `NotificationError` as the base exception for operational notification
delivery failures.

`NotificationError` must not be used for invalid public argument types.

---

## ConsoleNotificationChannel

Public package:

```text
infrastructure.notifications.console
```

Public export:

- `ConsoleNotificationChannel`

Constructor:

```python
__init__(stream: TextIO) -> None
```

The stream must expose callable `write()` and `flush()` members. An invalid
stream raises `TypeError`.

Public method:

```python
send(notification: Notification) -> None
```

An invalid notification argument raises `TypeError`.

The channel writes exactly one line:

```text
{notification.created_at.isoformat()} {notification.product_id.value} {notification.message}\n
```

The channel flushes the stream after writing.

`OSError` or `ValueError` raised by `write()` or `flush()` is wrapped in
`NotificationError` with the original exception as its cause.

The implementation must not default to `sys.stdout`. The Application layer
will inject the output stream when it composes the channel.

---

## Dependency Rules

`core.notifications` may import only:

- `core.domain`
- the public `core.rules` API
- Python standard library modules

`core.notifications` must not import:

- Infrastructure
- Applications
- provider implementations
- HTTP libraries
- databases
- Home Assistant

Infrastructure console delivery may import Core notification contracts and
domain objects.

No Application package is implemented in this story.

---

## Determinism

Core notification generation must not use:

- `datetime.now()`
- `datetime.utcnow()`
- `uuid4()`
- random values
- environment variables
- filesystem, network or database access

Equal inputs produce equal notification values.

---

## Tests

Provide unit tests covering:

- matching evaluation generates the specified `Notification`
- non-matching evaluation returns `None`
- all invalid `NotificationEngine` argument types raise `TypeError`
- equal inputs produce equal notification values
- `NotificationChannel` Protocol compatibility
- Console channel public export
- exact console output format
- stream flush after delivery
- invalid stream raises `TypeError`
- invalid notification raises `TypeError`
- write failure is wrapped in `NotificationError`
- flush failure is wrapped in `NotificationError`
- wrapped delivery failures preserve their cause
- Core and Infrastructure public exports
- Core dependency boundaries
- Core never reads the system clock or generates UUIDs

Tests must not use real console output, network access, files or databases.

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0006 is followed exactly.
- Notification generation is deterministic and side-effect free.
- Core contains no concrete notification channel.
- Console delivery belongs to Infrastructure.
- Application composition remains outside this story.
- Public APIs are exported through `__init__.py`.
- All public objects have type hints and docstrings.
- Invalid public argument types raise `TypeError`.
- Operational delivery failures raise `NotificationError`.
- No existing Domain, Provider SDK, Rule Engine or State Store public API is
  changed.
- No TODOs, placeholders, pass statements, commented-out code or dead code
  remain.
- All tests pass with 100% statement and branch coverage.
