# STORY-018: Twenty-Percent Price Alerts

## Objective

Implement durable reference-price evaluation and normal-operation
deduplication for catalog-mode Home Assistant monitoring according to
ADR-0019.

## Scope

Create Core price-reference and notification-reservation APIs, extend the
existing synchronization workflow through optional collaborators, add SQLite
schema version 3 and its reservation adapter, and enable the feature only in
Home Assistant catalog mode.

Do not change Domain fields, Provider SDK signatures, catalog discovery,
refresh ordering, CLI composition, JSON persistence or explicit Home Assistant
mode behavior.

## Core Public API

`core.rules` exports `PriceReferencePolicy` with the exact `enrich()` contract
from ADR-0019.

`core.notifications` exports:

- `NotificationReservation`
- `NotificationReservationStore`
- `NotificationReservationError`
- `PriceDropReservationPolicy`

All value objects are frozen and slotted. Public APIs validate types before
performing work. Reservation timestamps must be timezone-aware. Money remains
`Decimal` based.

`PriceDropEvaluator` must:

- prefer `current.original_price` over `previous.current_price`;
- preserve existing behavior when no current reference exists;
- accept optional boolean `available_only`;
- reject a non-boolean `available_only` with `RuleError`;
- avoid division by zero;
- remain deterministic and side-effect free.

`NotificationEngine` appends reference and discount details only when a
reference is present. Its public signature remains unchanged.

## Synchronization Public API

Add the four optional keyword-only constructor parameters defined by ADR-0019.
Both collaborator pairs are all-or-none. Validate them structurally without
calling dependencies.

Add `suppressed_notification_count: int = 0` to
`SynchronizationResult`. Reject `bool`, negative values and non-integers.

Workflow ordering and error handling must exactly follow ADR-0019. Existing
callers that omit the new dependencies retain their former calls, results and
identifier consumption.

## SQLite Persistence

Upgrade the shared schema constant to version 3.

Fresh databases create the reservation table directly. Valid version-1 and
version-2 databases migrate sequentially and transactionally without changing
catalog or observation values. Exact schema validation includes the new table.

`SqliteNotificationReservationStore` implements atomic reserve and idempotent
release. Canonical UUID, supported `RuleType`, supported currency, finite
non-negative Decimal and timezone-aware datetime decoding are mandatory.
Malformed persisted data and SQLite failures raise
`NotificationReservationError` with chaining.

## Home Assistant Catalog Mode

Catalog composition injects:

- the shared `SqliteStateStore` as `ObservationHistory`;
- `PriceReferencePolicy`;
- `SqliteNotificationReservationStore` using the catalog database path;
- `PriceDropReservationPolicy`.

The catalog price-drop rule includes `available_only=True`. A missing catalog
percentage becomes `Decimal("20.00")`. The packaged default changes from
`10.00` to `20.00`.

Catalog cycle output includes `suppressed_notifications`. Explicit cycle output
is unchanged.

## Tests

Cover:

- every reference selection, currency, zero-price and validation branch;
- evaluator original-price preference, availability and compatibility paths;
- reservation immutability, policy behavior and public exports;
- workflow enrichment order, new reservation, duplicate suppression, release
  on failure and reservation retention after snapshot failure;
- result count validation and backward-compatible construction;
- fresh schema 3 and exact sequential migrations from versions 1 and 2;
- atomic reserve, idempotent release and every adapter error boundary;
- catalog-only Home Assistant composition and 20-percent default;
- notification body reference details;
- an integration sequence of baseline, qualifying drop and unchanged repeat.

Tests use fakes and temporary local SQLite databases and never access the
network.

## Acceptance Criteria

- an available current price at exactly 80 percent of its reference matches;
- a price above 80 percent, unavailable product or missing reference does not;
- the reliable current original price wins over historical observations;
- historical fallback is the highest prior same-currency current price;
- the first observation establishes history without an alert;
- an equal reserved product price does not send again across store reopen;
- a different qualifying price may send once;
- explicit Home Assistant and CLI behavior remain backward compatible;
- schema migrations preserve catalog and observation data exactly;
- all public APIs are exported through `__init__.py` and documented;
- no TODOs, placeholders, skipped tests, commented code or dead code remain;
- the complete suite has 100 percent statement and branch coverage.
