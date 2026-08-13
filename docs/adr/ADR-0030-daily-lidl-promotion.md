# ADR-0030: Daily Lidl Promotion in the Discount Digest

## Status

Accepted

## Context

Lidl Czech Republic publishes a prominent global marketing message above its
online shop navigation. The message changes over time and may describe a
single-day offer, promotion code or delivery benefit. The operator wants the
current message included near the top of the existing daily Parkside discount
email.

The message is provider metadata rather than a product, price rule or Home
Assistant concern. Lidl renders it in server-supplied HTML on its public home
page with the CSS class `n-navigation__marketing-message--label` and an
optional surrounding link. Fetching and parsing it must remain outside Core,
while selection and digest formatting must remain deterministic.

The feature must not make continuous catalog monitoring fail when the
marketing page is temporarily unavailable. It must also avoid sending the
daily digest without the promotion merely because the first eligible lookup
failed.

## Decision

Core adds the provider-neutral `core.promotions` package containing an
immutable `DailyPromotion`, a `DailyPromotionSource` Protocol and
`PromotionError` for operational source failures.

`DailyPromotion` contains non-blank display text and an optional absolute
HTTPS URL. Core does not know Lidl, HTML, HTTP, the system clock or Home
Assistant.

Infrastructure adds `LidlMarketingPromotionSource` to
`infrastructure.providers.lidl`. It uses the existing injected
`TextHttpClient` to retrieve `https://www.lidl.cz/` and parses the first global
marketing label in document order. Whitespace is normalized. An absent label
returns `None`. A link is retained only when it resolves to HTTPS on
`lidl.cz` or `www.lidl.cz`; invalid external data and HTTP failures raise
`PromotionError` with the original cause chained.

The reusable daily-digest workflow accepts an optional promotion source. It
performs no promotion lookup before the configured delivery time or after the
date is already reserved. After creating a new date reservation it requests
the current promotion before reading snapshots. A `PromotionError` releases
the reservation and returns `PROMOTION_UNAVAILABLE`, allowing the next normal
catalog cycle to retry without stopping monitoring. A valid `None` result
sends the ordinary digest. Other generation, persistence and delivery failure
semantics remain unchanged.

The deterministic digest engine accepts an optional `DailyPromotion`. When
present, the message places its text and optional URL directly after the date
heading and before the discount threshold. This applies to both non-empty and
empty product digests.

Home Assistant catalog composition enables the source whenever the existing
daily digest is enabled. No new App option, persistence table, scheduler,
sensor or credential is introduced.

## Public API

`core.promotions` exports:

```python
@dataclass(frozen=True, slots=True)
class DailyPromotion:
    text: str
    url: str | None = None

class DailyPromotionSource(Protocol):
    def current(self) -> DailyPromotion | None: ...

class PromotionError(Exception): ...
```

`DailyDiscountDigest` gains the backward-compatible final field:

```python
promotion: DailyPromotion | None = None
```

`DailyDiscountDigestEngine.generate(...)` gains the backward-compatible final
argument `promotion: DailyPromotion | None = None`.

`DailyDigestWorkflow(...)` gains the keyword-only optional dependency
`promotion_source: DailyPromotionSource | None = None`.

`DailyDigestStatus` gains `PROMOTION_UNAVAILABLE`. `DailyDigestResult` gains
the backward-compatible boolean field `promotion_included=False`, which may be
true only for `SENT`.

`infrastructure.providers.lidl` exports `LidlMarketingPromotionSource`.

## Failure and Retry Semantics

- an absent marketing label is not an error and sends the digest without it;
- an HTTP, decoding or malformed-banner failure produces
  `PROMOTION_UNAVAILABLE`, releases the new daily reservation and retries on a
  later catalog cycle;
- no snapshot read or notification delivery occurs on that retry outcome;
- a successfully sent digest remains protected by the existing date
  reservation and is never resent merely because the banner later changes;
- failures outside promotion lookup retain ADR-0020 behavior.

## Dependency Direction

```text
applications.daily_digest --> core.promotions
applications.homeassistant --> infrastructure.providers.lidl
infrastructure.providers.lidl --> core.promotions + infrastructure.http
core.notifications --> core.promotions
```

Core remains deterministic and infrastructure-independent. The existing
Provider SDK product contract is unchanged.

## Alternatives Considered

### Add the banner to Product

Rejected because the global promotion is not product state and would be
duplicated across every catalog product.

### Parse one selected product page

Rejected because the promotion is global and the home page is its stable
provider-level source; tying it to a retained product adds an unnecessary
availability dependency.

### Send the digest without the promotion after an HTTP failure

Rejected because that would consume the one daily reservation and permanently
omit the requested information for that day. A bounded retry on the existing
cycle cadence is more useful and does not add a scheduler.

### Propagate the failure and stop the App

Rejected because optional marketing metadata must not stop catalog price and
availability monitoring.

## Consequences

The daily email includes the current global Lidl offer and its actionable link
when published. One additional public HTTP request occurs only on the first
eligible digest attempt for a date, plus retries after operational failure.
The integration depends on a documented HTML selector and will visibly retry
rather than silently send incomplete content if that structure becomes
malformed.
