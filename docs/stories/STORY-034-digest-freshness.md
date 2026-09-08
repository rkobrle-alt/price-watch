# STORY-034: Daily Digest Freshness

## Status

Implementation-ready. Implements ADR-0035 for v1.2.0.

## Scope and public API

Implement the policy and Protocol specified by ADR-0035 in
`core.notifications.digest_freshness`; export both from `core.notifications`.
Extend the existing engine, workflow and result with exactly the optional
arguments/field in that ADR. Compose a private adapter in
`applications.homeassistant.digest_refresh`, reusing the current batch
synchronizer with empty rules. Append its optional composition parameter to
the existing digest composition helper. Use product URLs for requests;
transient ProductReference objects use their URL as opaque external ID and are
never passed to catalog persistence. Process batches of at most 25, selected
by the Core policy with a total limit of 200 products.

## Behavior

- Reserve date and retrieve promotion before any preflight product requests.
- Select only qualifying stale/future-dated products, oldest then UUID.
- Reuse current price enrichment and append successful observations.
- Reload snapshots after preparation and recompute the final digest.
- Keep stale qualifying products but mark them `NEOVĚŘENO V POSLEDNÍ HODINĚ`.
- Mark recent ones `OVĚŘENO V POSLEDNÍ HODINĚ` and show each observation's
  cycle-start timestamp in ISO format with offset, preserving new/other sections.
- Include aggregate recent/unverified counts and explain the one-hour window
  and that prices/availability can change after checking.
- Log preparation errors separately and feed them into operational/weekly
  classification as documented. Existing dashboard catalog aggregates retain
  the ordinary-cycle meaning and catch up on the following cycle.
- Keep one daily email, baseline comparison, promotion retry and reservation
  compensation. Preserve SQLite schema 7 and all existing App options.

## Acceptance and tests

Network-free tests must cover exact one-hour boundary, future timestamps,
qualification, deterministic oldest-first ordering, cap and tie-breaker,
invalid types/values and explicit exports. Verify per-product times and counts,
empty output, unchanged legacy formatting, and new/existing sections.

Verify preparation is skipped for not-due, already-sent and failed-promotion
outcomes; runs before baseline/delivery; reload removes sold-out or no-longer
discounted products; failed refresh retains an honestly labelled observation;
refresher contract/programming/persistence errors release reservations.
Verify serial batching, empty rules, partial errors, shared composition,
operational logging/classification and restart suppression using SQLite.

Run the complete test suite and dependency checks with 100% statement and
branch coverage. Update operator documentation, changelog and synchronized
release identity to 1.2.0. Prepare logical commits after review. Deployment
verification must distinguish repository completion from the running HA version.
