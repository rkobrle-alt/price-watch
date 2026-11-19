# STORY-040: Exclude confirmed missing product pages

Implement ADR-0036 in HTTP transport, Lidl provider, Core freshness policy and
daily workflow. Preserve history, reservation and transient-failure semantics.
Add exported typed exceptions and a deterministic after_refresh policy. No
external search, state migration, notification resend or new scheduler.

Acceptance: classify real HTTP 404/410 distinctly; never infer missing from
error message text. Keep 403/429/500/timeouts as ordinary transport failures.
Filter only exact matching missing URLs before baseline staging; preserve
unrelated snapshots and all diagnostics. Test a returning page, unchanged
SQLite history, same-day duplicate protection, and invalid new API inputs.
Run the complete suite with 100% statement and branch coverage.

Readiness: implementation-ready; boundaries, API and validation reviewed.
