# ADR-0020: Daily Discount Digest

## Status

Accepted

---

## Context

Catalog monitoring now discovers Parkside products, retains exact observations
and sends durable alerts for qualifying individual prices. The operator also
wants one optional daily email summarizing all currently available products
whose approved discount is at least the configured price-drop percentage.

The interval scheduler is deliberately fixed-delay and has no calendar
semantics. Replacing it with a second scheduler would duplicate process
orchestration. A daily decision can instead be evaluated after every completed
catalog cycle from the caller-supplied timestamp.

The digest must survive App restarts without repeating the same calendar day.
SQLite and Home Assistant delivery cannot be atomic, so the same explicit
crash boundary accepted for individual alerts applies to digest delivery.

---

## Decision

Core defines the immutable digest, deterministic selection and formatting
service, delivery Protocol and reservation Protocol. A reusable Application
workflow owns calendar eligibility and orchestration. SQLite implements the
query and reservation boundaries. Home Assistant provides the concrete digest
delivery channel.

The feature is available only in Home Assistant catalog mode. It is disabled
by default and does not change explicit Home Assistant or CLI behavior.

---

## Home Assistant Options

The App accepts:

- `daily_digest_enabled`, optional boolean, default `false`;
- `daily_digest_time`, optional local wall-clock string in exact `HH:MM`
  24-hour form, default `08:00`.

`daily_digest_time` is valid only when the digest is enabled. Enabling the
digest requires catalog mode. The minimum discount reuses the catalog
`price_drop_percentage`; there is no independent threshold. Enabling the
digest while that percentage is explicitly absent is invalid configuration.

The calendar timezone is fixed to `Europe/Prague`. It is not configurable in
this version. The standard-library `zoneinfo` database determines daylight-
saving transitions. The official Python `tzdata` package is an explicit
runtime dependency so the same IANA data is available on platforms, including
Windows and minimal containers, which do not supply a system timezone database.

---

## Core Public API

`core.state` exports:

```python
class LatestSnapshotReader(Protocol):
    def latest_snapshots(self) -> tuple[StateSnapshot, ...]: ...
```

The result contains at most one last-inserted snapshot for every observed
product in deterministic product-ID order.

`core.notifications` exports:

```python
@dataclass(frozen=True, slots=True)
class DailyDiscountDigest:
    calendar_date: date
    created_at: datetime
    products: tuple[Product, ...]
    message: str
```

```python
class DailyDiscountDigestEngine:
    def generate(
        self,
        snapshots: tuple[StateSnapshot, ...],
        minimum_discount: Percentage,
        calendar_date: date,
        timestamp: datetime,
    ) -> DailyDiscountDigest: ...
```

```python
class DailyDiscountDigestChannel(Protocol):
    def send(self, digest: DailyDiscountDigest) -> None: ...
```

```python
class DailyDigestReservationStore(Protocol):
    def reserve(self, calendar_date: date, reserved_at: datetime) -> bool: ...
    def release(self, calendar_date: date) -> None: ...
```

`DailyDigestReservationError` reports digest-reservation persistence failures.

ADR-0030 extends the digest with an optional provider-neutral
`DailyPromotion`, adds a backward-compatible optional promotion argument to
the engine and stores the supplied promotion on `DailyDiscountDigest`. Product
selection and all calls which omit the promotion remain unchanged.

The engine includes only products which are available, expose an approved
`original_price`, and have `discount_percent` greater than or equal to the
minimum. Products are ordered by descending discount, then case-insensitive
name and product UUID. Duplicate product identifiers in the supplied snapshot
tuple raise `ValueError`. Equal inputs produce an equal digest.

The message contains the local date, threshold, qualifying count and each
product's name, current price, reference price, exact discount and URL. An
empty qualifying set produces a valid message saying that no matching
products are currently available. The empty digest is still delivered.

The exact non-empty message shape is:

```text
Parkside daily discount digest — {calendar_date.isoformat()}
Minimum discount: {minimum_discount.value}%
Discounted products: {count}

1. {product.name}
Current price: {current amount} {currency}
Reference price: {reference amount} {currency}
Discount: {discount_percent.value}%
URL: {product.url}
```

Product blocks are separated by one blank line. The empty shape retains the
three header lines, one blank line and ends with:

```text
No currently available products match the discount threshold.
```

Invalid public argument types raise `TypeError`. Naive timestamps and invalid
values raise `ValueError`. Core performs no I/O, clock reads or timezone
lookup.

---

## Application Workflow

The reusable package is:

```text
applications.daily_digest
```

It exports immutable `DailyDigestConfig`, `DailyDigestResult`,
`DailyDigestStatus` and `DailyDigestWorkflow`.

```python
class DailyDigestStatus(str, Enum):
    NOT_DUE = "not_due"
    ALREADY_SENT = "already_sent"
    SENT = "sent"
```

```python
@dataclass(frozen=True, slots=True)
class DailyDigestConfig:
    delivery_time: time
    minimum_discount: Percentage
```

The delivery time is a naive local wall-clock value with zero seconds and
microseconds. The timezone is a separate workflow dependency.

```python
@dataclass(frozen=True, slots=True)
class DailyDigestResult:
    calendar_date: date
    status: DailyDigestStatus
    product_count: int = 0
```

`product_count` is the number included in a sent digest and zero for the two
non-delivery statuses.

ADR-0030 adds `PROMOTION_UNAVAILABLE` and the backward-compatible
`promotion_included` result flag. The new status is a non-delivery retry
outcome and therefore also has zero products.

```python
DailyDigestWorkflow(
    snapshot_reader: LatestSnapshotReader,
    reservation_store: DailyDigestReservationStore,
    digest_engine: DailyDiscountDigestEngine,
    digest_channel: DailyDiscountDigestChannel,
    config: DailyDigestConfig,
    timezone: tzinfo,
)
```

```python
run(timestamp: datetime) -> DailyDigestResult
```

The status is one of `NOT_DUE`, `ALREADY_SENT` or `SENT`. On every completed
catalog cycle the workflow converts the supplied timestamp to the injected
timezone. Before the configured wall-clock time it returns `NOT_DUE` without
persistence access. At or after that time it:

1. reserves the local calendar date;
2. returns `ALREADY_SENT` when the date already exists;
3. loads the latest snapshots;
4. generates and sends one digest;
5. returns `SENT` with the qualifying product count.

Generation or delivery failure releases a newly created reservation and
propagates. A successful delivery keeps it. A hard process termination after
reservation but before Home Assistant accepts the message can suppress one
undelivered digest. This avoids repeated daily emails and is accepted because
the notify service has no idempotency key.

The first App cycle at or after the configured time sends the digest, including
after a restart. A cycle before the configured time does not send. Exactly one
reservation identity exists per Europe/Prague calendar date.

---

## SQLite Schema Version 4

Schema version 4 adds `daily_digest_reservations` with canonical ISO calendar
date and timezone-aware reservation timestamp. The calendar date is the
primary key.

Fresh databases create version 4 directly. Valid versions 1, 2 and 3 migrate
sequentially and transactionally to version 4 without changing catalog,
refresh, observation or price-alert reservation values.

`SqliteStateStore` implements `LatestSnapshotReader`.
`SqliteDailyDigestReservationStore` implements the digest reservation
Protocol with the existing SQLite constructor form:

```python
SqliteDailyDigestReservationStore(path: Path, timeout_seconds: int = 5)
```

Both remain independent of Applications and Home Assistant.

---

## Home Assistant Integration

Catalog composition creates `DailyDigestWorkflow` only when enabled. It uses
the shared catalog SQLite database, the configured notify entity and a title
derived from the existing notification title with ` Daily Digest` appended.

`infrastructure.notifications.homeassistant` exports:

```python
HomeAssistantDailyDiscountDigestChannel(
    client: HomeAssistantClient,
    entity_id: str,
    title: str = "Price Watch Daily Digest",
)
```

Its `send(digest)` method invokes the same `notify.send_message` service and
translates `HomeAssistantError` to `NotificationError`.

The digest runs after catalog synchronization and status publication using the
same cycle timestamp. When enabled, its outcome is appended to the catalog
cycle summary as `digest_status` and `digest_products`. Disabled catalog output
remains unchanged.
Digest persistence and delivery failures retain their subsystem exceptions and
stop the scheduler like other mandatory configured notification failures.
ADR-0030 makes only an operational promotion lookup failure non-fatal: its new
reservation is released and a later catalog cycle retries before any digest is
sent. All other failures retain this behavior.

---

## Dependency Direction

```text
applications.homeassistant
    +--> applications.daily_digest
    +--> Infrastructure SQLite and Home Assistant adapters

applications.daily_digest --> Core notification and state contracts

infrastructure.persistence.sqlite --> Core contracts
infrastructure.notifications.homeassistant --> Core digest contract
```

Core imports neither Applications, SQLite nor Home Assistant.

---

## Consequences

Advantages:

- one restart-safe daily overview at a predictable Czech local time;
- exact reuse of approved discounts and Decimal values;
- no second scheduler, credential store or SMTP implementation;
- deterministic, independently testable selection and formatting;
- unchanged CLI and explicit Home Assistant mode.

Costs:

- the digest reflects the latest successfully observed state, whose products
  may have been refreshed at different times;
- SQLite schema gains another durable reservation table;
- the accepted reservation-before-delivery crash window remains;
- a configured digest delivery failure stops the current App run.
