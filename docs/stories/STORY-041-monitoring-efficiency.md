# STORY-041: Monitoring efficiency

Implement ADR-0037 across Core catalog policy, optional reusable catalog
workflow collaborators, SQLite missing-page persistence, HA composition and
health classification. Add explicit exported APIs with type hints/docstrings.

Acceptance: test 24-hour preview cadence, startup, failed publication, manual
refresh and digest-before-preview order. Test missing-page delay boundaries,
repeated failures, restart persistence, transient failures, provider isolation,
new URL, recovery and exclusion outside the digest budget. Test schema 7→8
migration, rollback on failure, validation and preservation of history and daily
reservations. Partial failures remain degraded; three severe failures escalate;
known missing pages alone do not fail health. Run full suite and 100% coverage,
CI and multiarch publication, preserve pre-update backup and verify live cycle.

Readiness: implementation-ready; scope, validation and dependency boundaries
reviewed against accepted ADRs. User authorized publication and deployment.
