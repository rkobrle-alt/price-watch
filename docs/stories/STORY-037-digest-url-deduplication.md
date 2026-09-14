# STORY-037: Deduplicate Digest Refresh Requests

## Status

Implementation-ready for patch 1.2.3 under ADR-0007 and ADR-0035.

## Scope

Fix the private Home Assistant digest refresher handing duplicate URLs to the
Lidl provider, which requires unique request URLs. Distinct product IDs may
share a URL in persisted snapshots; this does not justify deleting history or
relaxing provider validation.

In `applications.homeassistant.digest_refresh`, deduplicate exact URL strings
across the complete selected input before batching. Retain the first occurrence
and its provider ID, preserve relative order and send at most 25 unique URLs
per batch. No URL canonicalization, product-ID merging, extra candidate
selection, retries or public API changes. Retain existing error aggregation
and empty-rule behavior.

Successful observations remain keyed by the actual product ID returned by the
existing provider/workflow. Do not copy observations to another product ID
sharing the URL or falsely mark that older identity fresh. The final digest
continues to use existing selection and freshness semantics.

## Tests and acceptance

- Test duplicates within and across batch boundaries, including different
  product IDs and repeated identical products; retain first occurrence/order.
- Verify empty input and error aggregation remain compatible.
- Integrate real provider validation, synchronization and SQLite with two
  stale IDs sharing a URL: one request, successful digest, preserved histories,
  older alias still labelled stale, no individual alerts and no resend after
  workflow reconstruction on the same date.
- Full test suite and dependency gates: 100% statement and branch coverage.
- Update operator notes and synchronized release identity to 1.2.3; preserve
  architecture, schemas, settings and existing reservation compensation.
- After review, publish the approved release and deploy to HA. Verify the
  runtime and digest state; do not delete today's reservation or force email.
