# ADR-0035: Daily Digest Freshness

## Status

Accepted for v1.2.0 under the approved daily-summary freshness milestone.

## Decision

Before generating a newly reserved Home Assistant daily digest, refresh up to
200 currently qualifying products whose latest successful snapshot is older
than one hour. Future-dated snapshots also require verification. Oldest
timestamps come first, with product UUID as a stable tie-breaker. Qualification
reuses the existing digest engine. Already fresh products need no extra request.

The optional Application collaborator uses the existing synchronization stack,
with no rules, in serial batches of at most 25. It preserves reference-price
enrichment and observation history. These bounded extra requests belong only
to digest preparation; they do not change ordinary catalog rotation or its
recorded attempts. No discovery identities are created or persisted.

Preparation runs after date reservation and successful optional promotion
lookup, before baseline loading/staging and notification delivery. It is never
called before delivery time or for an already reserved date. Reload snapshots
after preparation so changed prices and availability affect qualification.
Failures returned by the provider retain previous observations, are logged and
contribute PARTIAL_PROVIDER_FAILURE to operational/weekly reporting when no
higher-priority ordinary catalog/provider failure exists. Persistence and
unexpected failures propagate through existing compensation.

The email includes the successful observation timestamp for each listed
product, plus counts verified within one hour and not recently verified.
Age uses the supplied cycle timestamp; recorded timestamps identify the
observation cycle start, not an exact per-response or email delivery time.
Age from zero through one hour inclusive is recent. Future timestamps are
unverified. Old or failed/budget-excluded products remain visible with an
explicit warning, without claiming fresh availability. Freshness does not
alter the qualifying set or the new/returning baseline by itself.

## Public API and boundaries

`core.notifications` exports deterministic `DigestFreshnessPolicy.select(
snapshots, minimum_discount, timestamp, limit=200) -> tuple[Product, ...]`
and `DigestProductRefresher` Protocol with `refresh(products, timestamp) ->
tuple[ProviderError, ...]`. Core performs no side effects.

`DailyDiscountDigestEngine.generate` appends `include_freshness: bool = False`.
Existing calls retain their message output. `DailyDigestWorkflow` gains the
optional keyword `product_refresher: DigestProductRefresher | None = None`.
When supplied it invokes the policy/refresher and enables freshness formatting.
`DailyDigestResult` appends `refresh_errors: tuple[ProviderError, ...] = ()`;
non-delivery results cannot contain refresh errors.

Home Assistant composes a private Lidl adapter using existing provider,
synchronization and SQLite dependencies. The reusable daily workflow depends
only on Core. No new persistent schema, option, permission, channel or scheduler
is introduced. Existing Python call forms and omitted-collaborator behavior
remain compatible. The managed catalog digest adopts preparation in v1.2.0.

Invalid public types raise TypeError; nonpositive limits, duplicate snapshot
IDs and naive timestamps raise ValueError. Returned refresher errors must be a
tuple of ProviderError instances.

## Trade-offs

This extends the ADR-0020/0032 digest sequence without changing reservations
or the accepted reservation-before-delivery process-crash boundary. Extra
network work lengthens that existing boundary and may delay the morning email.
The scheduler remains serial. A hard crash during preparation can suppress
the reserved day's email; watchdog recovery cannot remove that known trade-off.

Refreshing the complete catalog before email would cause unnecessary requests.
Dropping every stale observation would hide potentially useful offers and
distort the new-discount baseline. Bounded targeted refresh plus truthful
warnings provides useful evidence even during upstream outages. It cannot
guarantee stock or price at purchase time.
