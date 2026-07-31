# STORY-008: Application Workflow

## Goal

Implement the reusable application workflow defined by ADR-0009. The workflow
must connect providers, previous state, rule evaluation, notification
generation, notification delivery and current-state persistence without
changing their existing public APIs.

---

## Package Structure

Create:

```text
applications/
    __init__.py
    synchronization/
        __init__.py
        result.py
        workflow.py

tests/unit/applications/
    __init__.py
    helpers.py
    test_architecture.py
    test_public_api.py
    test_synchronization_result.py
    test_synchronization_workflow.py
```

---

## Public API

Export through `applications.synchronization`:

- `SynchronizationWorkflow`
- `SynchronizationResult`

Every public object and method must have explicit type hints and docstrings.

---

## SynchronizationWorkflow

Constructor:

```python
__init__(
    providers: tuple[Provider, ...],
    state_store: StateStore,
    rule_engine: RuleEngine,
    notification_engine: NotificationEngine,
    notification_channel: NotificationChannel,
    notification_id_factory: Callable[[], UUID],
) -> None
```

Requirements:

- `providers` is a non-empty tuple of structural `Provider` implementations
- each provider exposes `ProviderId`, non-blank display name and version, and
  a callable `fetch`
- `state_store` exposes callable `load` and `save`
- `rule_engine` exposes callable `evaluate`
- `notification_engine` exposes callable `generate`
- `notification_channel` exposes callable `send`
- `notification_id_factory` is callable
- invalid argument types raise `TypeError`
- an empty provider tuple or blank provider metadata raises `ValueError`
- construction performs no provider, persistence or delivery operation

Public method:

```python
run(
    rules: tuple[Rule, ...],
    timestamp: datetime,
) -> SynchronizationResult
```

Requirements:

- `rules` must be a tuple containing only `Rule` instances
- `timestamp` must be a timezone-aware `datetime`
- invalid types raise `TypeError`
- a naive timestamp raises `ValueError`
- providers are fetched in constructor order
- a raised `ProviderError` is recorded and the next provider is fetched
- successful `FetchResult.errors` are recorded in returned order
- products are processed in `FetchResult.products` order
- every rule is applied to every product in rule order
- previous state is loaded using `product.id`
- `RuleEngine.evaluate()` receives the previous product or `None`, the
  current product and the supplied timestamp
- `NotificationEngine.generate()` is invoked for every evaluation with the
  next value from `notification_id_factory`
- generated notifications are sent immediately and retained in result order
- no notification is sent when generation returns `None`
- after all rules for a product complete, its current snapshot is saved with
  the supplied timestamp
- products are saved even when `rules` is empty or no rule matches
- State Store, Rule Engine, notification, identifier-factory and unexpected
  provider failures propagate unchanged
- completed side effects are not compensated after a later failure

---

## SynchronizationResult

Create a frozen, slotted dataclass with fields:

```python
fetch_results: tuple[FetchResult, ...]
evaluations: tuple[EvaluationResult, ...]
notifications: tuple[Notification, ...]
snapshots: tuple[StateSnapshot, ...]
provider_errors: tuple[ProviderError, ...]
```

Validation requirements:

- every field must be a tuple containing only the declared object type
- invalid field values raise `TypeError`
- the object remains immutable

---

## Ordering and Failure Semantics

Returned tuples contain only completed operations and preserve provider,
product and rule processing order.

Notification delivery precedes persistence for each product. If delivery
fails, the product snapshot is not saved. If delivery succeeds and saving
fails, a retry may deliver the logical notification again.

The workflow performs no retries, rollback, deduplication, logging or error
translation.

---

## Dependency Rules

Production code may import only:

- public `core.domain`
- public `core.provider`
- public `core.rules`
- public `core.state`
- public `core.notifications`
- Python standard library modules

It must not import concrete Infrastructure implementations, CLI, Home
Assistant, HTTP, database or environment configuration modules.

Core and Infrastructure must not import Applications.

No existing public API may be modified.

---

## Tests

Provide network-free and filesystem-free unit tests covering:

- constructor validation and absence of construction side effects
- public API exports, annotations and docstrings
- frozen result behavior and every result validation branch
- structural compatibility with fake providers, stores and channels
- provider, product and rule ordering
- previous state loading and first-observation behavior
- matched and non-matched notification generation
- one ID-factory invocation per evaluation
- snapshot timestamp and save-after-delivery ordering
- saving with no rules and no matching rules
- aggregation of returned provider errors
- isolation of a raised `ProviderError`
- propagation of State Store, Rule Engine, notification, ID-factory and
  unexpected provider failures
- no snapshot save after failed delivery
- preservation of completed earlier side effects after a later failure
- dependency direction
- absence of clock, randomness, environment, filesystem and network access

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0005, ADR-0006, ADR-0008 and ADR-0009 are followed.
- One workflow run composes the full approved synchronization sequence.
- Provider failures do not prevent later providers from running.
- Successful partial-provider products are processed despite returned errors.
- Every product is compared with its stored previous state.
- Every configured rule is evaluated for every product.
- Generated notifications are delivered before current state is saved.
- Current snapshots persist even when no rule matches.
- Core, Domain and existing Infrastructure public APIs remain unchanged.
- Applications contain orchestration only and no business rule logic.
- Public APIs are exported through `__init__.py`.
- No TODOs, placeholders, pass statements, commented-out code or dead code
  remain.
- All tests pass with 100% statement and branch coverage.

