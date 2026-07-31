# Synchronization Workflow Architecture

## Purpose

The synchronization application coordinates one complete pull-based cycle
without owning business rules or Infrastructure implementations.

---

## Package

```text
applications/synchronization/
    __init__.py
    result.py
    workflow.py
```

Responsibilities:

- `workflow.py` coordinates existing public contracts
- `result.py` defines the immutable application result
- `__init__.py` exports the public API

---

## Public API

The package exports:

- `SynchronizationWorkflow`
- `SynchronizationResult`

```python
SynchronizationWorkflow(
    providers: tuple[Provider, ...],
    state_store: StateStore,
    rule_engine: RuleEngine,
    notification_engine: NotificationEngine,
    notification_channel: NotificationChannel,
    notification_id_factory: Callable[[], UUID],
)
```

```python
run(
    rules: tuple[Rule, ...],
    timestamp: datetime,
) -> SynchronizationResult
```

---

## Processing Flow

```text
Provider.fetch
    |
    v
Product
    |
    v
StateStore.load(product.id)
    |
    v
RuleEngine.evaluate(rule, previous, current, timestamp)
    |
    v
NotificationEngine.generate(product, evaluation, supplied UUID)
    |
    +--> None
    |
    +--> NotificationChannel.send(notification)
    |
    v
StateStore.save(StateSnapshot(product, timestamp))
```

The sequence repeats in provider, product and rule order. The flattened result
retains that order.

---

## Result

`SynchronizationResult` is a frozen, slotted dataclass containing tuples of:

- `fetch_results`
- `evaluations`
- `notifications`
- `snapshots`
- `provider_errors`

It reports completed work only. If a non-provider operation raises, the
exception propagates and no result is returned.

---

## Error Boundary

Provider failures represented by `ProviderError` are isolated and collected.
Successful products from a partial `FetchResult` still complete the workflow.

State Store, Rule Engine and notification channel exceptions retain their
existing subsystem types and propagate unchanged.

Delivery occurs before persistence. This provides at-least-once notification
behavior and protects transition detection from permanent loss after a failed
delivery.

---

## Composition Boundary

The workflow depends on Core contracts, not concrete Infrastructure classes.

An outer application such as the CLI composes:

- `LidlParksideProvider`
- `JsonStateStore`
- configured `RuleEngine`
- `NotificationEngine`
- `ConsoleNotificationChannel`
- clock and UUID generation

The CLI supplies configuration and invokes `run()`; it does not reproduce the
workflow.

---

## Determinism and Side Effects

The application service reads neither clock, randomness nor environment.
Callers supply the cycle timestamp and notification ID factory.

HTTP, filesystem and delivery effects remain behind injected boundaries.

