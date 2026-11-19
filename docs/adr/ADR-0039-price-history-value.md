# ADR-0039: Observed price history and offer value

## Status

Accepted under explicit authorization to implement, test, publish and deploy
v1.5.0. This adds analysis; existing discount qualification, reference-price
selection, delivery reservations and notification count remain unchanged.

## Metrics and evidence

Core adds core.pricing with immutable PriceHistoryAssessment, PriceValueRating,
PriceHistoryEngine and PriceHistoryAssessmentSource Protocol. Evaluate one
current StateSnapshot, an iterable of historical StateSnapshots and an aware
as-of timestamp. Inject a timezone into the engine (HA uses Europe/Prague);
Core reads neither clock, network nor timezone database.

Only available observations of the same product and currency at or before
as-of are price evidence. Reject foreign product identities and invalid input
types. Ignore unavailable, foreign-currency and future observations. Include
the supplied current observation without relabelling its capture time. Within
a local calendar day, the latest timestamp is the closing price; equal-time
ties use the last supplied observation (SQLite insertion order; current last).

30/90-day windows are inclusive local dates: today and the preceding 29/89
dates, cut off at as-of. Minima use every eligible observation, retaining
intraday lows. The usual price is the exact Decimal median of daily closing
prices within the 90-day window excluding today. No observation-frequency or
duration weighting and no extrapolation through missing days. A minimum is
always the lowest observed price, never a guarantee about unobserved prices.

Report first available same-currency observation, retained history span in
calendar days, observed-day counts for both windows, prior-day sample count,
minima, usual price, current price versus usual and last daily price-drop date.
The last drop compares adjacent observed daily closing prices across retained
history; it is a detected daily comparison, not an exact intraday change time.
Retention can create gaps; span does not imply continuous coverage or original
monitoring start. No rows are deleted or rewritten and schema stays at 9.

## Ratings

- unverified: current unavailable, future-dated or older than one hour;
- insufficient_history: fewer than 7 prior observed days in the 90-day window;
- excellent: at least 10% below usual AND equal to the observed 90-day minimum;
- good: at least 10% below usual;
- lower: below usual by less than 10%;
- normal: equal to usual;
- above_usual: above usual.

If usual is zero, equality is normal and a higher price is above_usual; no
division by zero. Exact Decimal arithmetic determines thresholds. This is an
observed-data comparison, not a purchasing recommendation or an assertion
about market-wide price or legally defined discounts.

## Composition and output

DailyDigestWorkflow appends optional price_history_source. After freshness
preparation and normal qualifying selection, request assessments only for the
final digest products, then regenerate the deterministic formatted digest with
optional price_assessments. None retains all existing output/order. When
provided, require exactly one matching assessment per product, matching current
price, observation timestamp and as-of. Duplicate/missing/foreign evidence is
an explicit error, not an unsupported rating.

DailyDiscountDigest appends price_assessments=(). With assessments, rank within
the existing new/other sections by excellent, good, lower, normal, above_usual,
insufficient_history, unverified; then descending saving versus usual, existing
reference discount and stable name/ID. Do not change the qualifying set or novelty
membership. Add Czech metric lines and explain daily median and observed coverage.
Stale/short-history offers retain their warnings and are not called bargains.

Infrastructure adds SqlitePriceHistoryAssessmentSource. Read existing indexed
observations per requested product, stream decoded snapshots into Core, and
retain only a closing timestamp/amount per observed day plus rolling minima.
No full-catalog history materialization, new network requests, schema migration,
automatic send or maintenance deletion. Database/codec failures use StateStoreError
and existing safe pre-handoff retry compensation. Public new APIs are exported.

## Alternatives

Highest historical price remains the compatible qualification reference, but is
not enough to rate usefulness. Median of every sample overweights frequently
checked days; interpolation invents prices; a full-history object graph repeats
the resolved memory problem. A web dashboard and personal watchlists remain
separate future milestones. No new dependency, option or scheduler is required.
