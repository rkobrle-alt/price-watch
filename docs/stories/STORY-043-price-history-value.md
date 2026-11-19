# STORY-043: Price history and observed offer value

Implement ADR-0039 in Core pricing, streaming SQLite assessment source, optional
digest workflow/engine inputs and managed HA composition. Show Czech observed
30/90-day minima, daily-median usual price, sample/coverage, last detected daily
drop and conservative value rating in each included offer. Keep legacy calls,
qualification, novelty, history and delivery behavior compatible.

Acceptance: exact window and one-hour boundaries, timezone/day rollover,
frequency-independent median, ties/out-of-order insertion, intraday minima,
currency isolation, future/unavailable data, zero usual price, short history
and every rating. Validate contracts and mismatched evidence. Verify real
SQLite read-only streaming, history preservation, restart/duplicate protection,
banner fallback and safe preparation failures. Run full suite with 100% statement
and branch coverage, CI, multiarch build, pre-update backup and live App cycle.

Readiness: implementation-ready. Metrics, scope, thresholds, performance and
public compatibility reviewed; no unresolved design decisions.
