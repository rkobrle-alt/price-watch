# ADR-0019: Twenty-Percent Price Alerts

## Status

Accepted

---

## Context

Catalog monitoring retains exact observations, but the existing price-drop
rule compares only the latest two observations. It can therefore miss a
durable discount after an intermediate discounted observation and can emit the
same logical alert on every qualifying refresh.

The product goal is one actionable notification when an available product is
priced at no more than 80 percent of an approved reference price. Reference
selection is business policy and must remain deterministic in Core. Reading
history, reserving an alert and delivering through Home Assistant remain
side-effecting operations coordinated by Applications and Infrastructure.

SQLite and Home Assistant cannot participate in one atomic transaction. Exact
once-only delivery across a process crash is therefore impossible without an
idempotent downstream delivery API. The platform must define useful normal
operation semantics without claiming distributed exactly-once delivery.

---

## Decision

Core defines deterministic reference-price enrichment and a structured price
alert identity. The existing synchronization workflow accepts optional,
injected history and alert-reservation collaborators. Catalog-mode Home
Assistant composition enables them; explicit URL and CLI composition remain
unchanged.

The existing `RuleType.PRICE_DROP`, `Rule`, `RuleEngine` and evaluator
registration model remain authoritative. No new rule type is introduced.

---

## Reference Price Policy

`core.rules` exports:

```python
class PriceReferencePolicy:
    def enrich(
        self,
        current: Product,
        history: tuple[StateSnapshot, ...],
    ) -> Product: ...
```

The service is stateless and deterministic. It validates complete immutable
inputs and returns either the unchanged product or an immutable replacement.

Reference selection order is:

1. `current.original_price`, when supplied by the provider;
2. otherwise the highest historical `current_price` having the same currency;
3. otherwise no reference.

The current observation is not part of `history` when enrichment occurs.
Historical observations in other currencies are ignored. Equal highest prices
use the earliest value, which is immaterial because `Money` values are equal.

When a reference exists, the enriched product exposes it as
`original_price`. `discount_percent` is recomputed exactly as:

```text
max(0, (reference - current) * 100 / reference)
```

A zero reference produces zero percent. Decimal arithmetic is used throughout.
No input object is mutated.

The existing `PriceDropEvaluator` prefers `current.original_price` as its
comparison reference and otherwise retains its previous-product behavior.
The optional boolean rule parameter `available_only` prevents a match when the
current product is unavailable. Absence of the parameter preserves existing
behavior. Invalid parameter types raise `RuleError`.

Catalog mode supplies:

```text
percentage = Decimal("20.00")
available_only = True
```

unless the existing percentage option explicitly supplies another valid
threshold. New packaged installations default to `20.00`.

---

## Price Alert Identity

`core.notifications` exports:

```python
@dataclass(frozen=True, slots=True)
class NotificationReservation:
    product_id: ProductId
    rule_type: RuleType
    price: Money
```

and:

```python
class NotificationReservationStore(Protocol):
    def reserve(
        self,
        reservation: NotificationReservation,
        reserved_at: datetime,
    ) -> bool: ...

    def release(self, reservation: NotificationReservation) -> None: ...
```

`reserve()` atomically returns `True` only when it created a new reservation.
An existing equal reservation returns `False`. `release()` is idempotent.
`NotificationReservationError` reports persistence failures. Invalid public
argument types raise `TypeError`; naive timestamps raise `ValueError`.

`PriceDropReservationPolicy.create(rule, product, evaluation)` is a pure Core
service. It returns a reservation only for an enabled, matching
`PRICE_DROP` evaluation. The identity deliberately excludes the rule UUID and
reference price: the same logical product price and currency must remain
suppressed after rule configuration or reference evolution. A different
current amount or currency is a distinct alert.

Back-in-stock notifications are not reserved by this policy and retain their
transition semantics.

---

## Synchronization Behavior

`SynchronizationWorkflow` gains four optional keyword-only collaborators:

```python
observation_history: ObservationHistory | None = None
price_reference_policy: PriceReferencePolicy | None = None
notification_reservation_store: NotificationReservationStore | None = None
price_drop_reservation_policy: PriceDropReservationPolicy | None = None
```

Each pair must be supplied together or omitted together. Existing positional
construction remains compatible.

For each fetched product, history enrichment occurs before latest-state load
and rule evaluation. For a reservation-producing evaluation, the workflow:

1. atomically reserves the logical alert;
2. suppresses generation and delivery when the reservation already exists;
3. generates and sends the notification when newly reserved;
4. retains the reservation after successful delivery;
5. releases it when generation or delivery raises, then propagates the
   original failure unless release itself fails.

Snapshot persistence remains after all delivery work. A successful
notification followed by snapshot failure retains its reservation, so retrying
the unchanged price does not resend it.

`SynchronizationResult` adds non-negative
`suppressed_notification_count: int = 0`. The default preserves existing
construction.

Because the reservation is written before the external service call, a hard
process termination in that narrow interval can retain a reservation for a
message that was not delivered. Ordinary reported generation or delivery
failures release it and are retried. This at-most-once crash trade-off is
accepted because the downstream Home Assistant SMTP action has no idempotency
key and the approved product priority is avoiding repeated alert emails.

---

## SQLite Schema Version 3

Schema version 3 adds `notification_reservations` with exact structured
columns for product UUID, rule type, currency, Decimal amount and timezone-
aware reservation timestamp. Its unique key is product, rule type, currency
and price amount.

Opening a valid version-2 database migrates it transactionally to version 3.
Catalog entries, refresh ordering and observations are preserved exactly.
Fresh databases create version 3 directly. Valid version-1 databases continue
through the accepted sequential 1 to 2 to 3 migrations in one open operation.
Unknown, malformed and future schemas remain rejected.

`infrastructure.persistence.sqlite` exports
`SqliteNotificationReservationStore`. It shares the existing explicit path and
has no dependency on Applications, Home Assistant or provider code.

---

## Notification Content

When `Product.original_price` is present, `NotificationEngine` appends exact
reference price and discount percentage lines to the existing channel-neutral
message. Products without a reference retain the previous text exactly.

---

## Dependency Direction

```text
applications.homeassistant
    +--> applications.synchronization
    +--> Infrastructure SQLite and notification adapters

applications.synchronization
    +--> Core rules, state and notification contracts

infrastructure.persistence.sqlite
    +--> Core notification reservation contract
```

Core performs no I/O and imports neither Infrastructure nor Applications.

---

## Consequences

Advantages:

- durable 20-percent comparison instead of latest-step comparison
- no repeated normal-operation email for the same product price
- exact Decimal and currency-aware reference handling
- unchanged explicit CLI and Home Assistant modes
- transactional sequential SQLite migration

Costs:

- catalog observations store the approved reference in `original_price`
- every catalog product performs a history read before evaluation
- strict no-duplicate preference creates the documented hard-crash loss window
- a later digest must query reservation and observation data separately
