# ADR-0037: Monitoring efficiency and product lifecycle

## Status

Accepted under the user's explicit request to implement and deploy improvements
1–3. Target release: 1.3.0.

## Decision

Run the daily digest before the optional retention preview. In each process,
recompute the preview at startup and then at most every 24 hours; keep the last
published timestamp honest. Failed publications remain retryable. Explicit
maintenance command previews always recompute; deletion still replans under
the operation lock and requires its existing expected count and backup.

SQLite schema 8 adds missing_product_pages(provider_id, url, failures,
checked_at, retry_at), with a composite primary key. Migrate transactionally
from schema 7 after validating the legacy schema; retain all other data.
Do not delete history or manufacture price/stock observations for HTTP errors.

Core defines MissingProductPage, MissingProductPageStore and MissingPagePolicy.
Only typed ProviderProductNotFoundError (404/410) records missing evidence.
Retries are 6 hours after the first response, 24 hours after the second, then
7 days after further responses. A successful fetch clears the record; transient
failures leave it intact. Earlier timestamps are rejected. Records survive
restart. The exact provider/URL pair is the identity; a new catalog URL remains
eligible without deleting old evidence. Daily digest and catalog summaries
exclude all known missing URLs until a successful normal retry restores them.

The optional catalog-workflow store filters the complete oldest-attempt order
before taking the bounded batch, so sleeping pages neither consume request
budget nor starve eligible pages. Existing callers without it retain behavior.
The Lidl composition records normal and digest-refresh outcomes with the same
store. SQLite operations use transactions, existing persistence error boundaries
and explicit validation. Public API additions preserve existing call forms.

Health ignores typed missing-page errors as upstream inventory churn. Partial
provider failures remain degraded regardless of duration. Severe consecutive
failures alone count toward the existing failed threshold; partial failures
must not accelerate escalation of a later full outage. Missing-page counts
remain visible separately in catalog diagnostics. Raw errors remain in logs.
The existing status sensor keeps its raw per-cycle provider-error meaning.

## Alternatives and limits

Deleting catalog rows would discard recovery context. Permanent retirement
would hide returning items. Rechecking every missing page wastes requests.
Moving retention to another concurrent worker would add unnecessary locking.
This design keeps one serial writer and bounded network work. Startup preview
still costs one scan, but follows email preparation. No new options or messages
are introduced. A rollback to 1.2.x cannot read schema 8; preserve a pre-update
App backup before deployment. Forward migration preserves reservations.
