# ADR-0036: Missing product pages in daily digests

## Status

Accepted for the requested correction of obsolete offers (2026-11-18).

## Evidence and decision

All 45 failed refresh URLs returned HTTP 404 again and were absent from the
current 1,797-product Parkside sitemap. Treating this evidence like a timeout
keeps obsolete offers in the daily email. A missing page is not fresh evidence
of a price or stock value; do not manufacture an unavailable-price snapshot.

Infrastructure exposes HttpResourceNotFoundError, a HttpClientError subtype,
for text HTTP 404 and 410 responses only. The Lidl adapter maps it to the
transport-neutral ProviderProductNotFoundError(message, url), a subtype of
ProviderTransportError with a validated nonblank URL attribute.

DigestFreshnessPolicy.after_refresh(snapshots, errors) returns snapshots whose
exact product URL was not reported missing in this preparation. The daily
workflow applies it after reloading observations and before baseline staging.
All errors remain in diagnostics. Timeouts, 403, 429, 5xx, malformed responses
and products outside the refresh budget retain ADR-0035 stale-data behavior.

No persistent tombstone, deletion, synthetic observation, schema migration or
automatic resend is introduced. Subsequent preparations still retry missing
pages; a returning product can re-enter the digest and its comparison baseline.
This deliberately does not claim stock unavailability or permanently retire a
product based on one 404. Ordinary monitoring errors remain observable.

## Boundaries and alternatives

Core owns the pure filtering policy and never sees HTTP status codes.
Infrastructure owns HTTP classification; Applications orchestrate the policy.
New API types are exported through package __init__.py. Existing catch sites
remain compatible through inheritance. Invalid URL types raise TypeError;
blank URLs raise ValueError. Policy inputs must be tuples of the declared types.

Persistent retirement would require lifecycle storage, migration and recovery
policy. Marking old prices freshly unavailable would falsify observation time.
Keeping confirmed missing pages as offers is the current defect. Requesting
search endpoints or inventing alternate product identities is not justified.

This narrowly amends ADR-0035's retention of failed observations for confirmed
missing pages in the current digest only; historical storage remains untouched.

## v1.3.0 amendment

ADR-0037 adds a 24-hour preview cadence, persistent missing-page retry evidence
and partial-failure health semantics. It supersedes the corresponding earlier
behavior while retaining explicit maintenance safeguards and observation history.
