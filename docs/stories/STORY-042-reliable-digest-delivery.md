# STORY-042: Reliable daily delivery and bounded promotion lookup

Implement ADR-0038 with deterministic Core contracts/policy, a reusable private
reliable-delivery coordinator, SQLite schema 9 and HA diagnostics/composition.
Refactor digest preparation for reuse without changing legacy call forms.

Acceptance: real SQLite restart tests cover crash before handoff, during handoff,
and after HA acknowledgement but before local acceptance. Claim/transition must
be atomic; a failed marker write must never dispatch. Preserve accepted/legacy
dates and product history; exclude uncertain candidate baselines. Test safe
rejection retry, ambiguous timeout no-resend, generic dispatch failure, channel
classification, preparation exceptions and baseline/persistence failures.
Test banner fallback before/at the deadline, late startup, normal None, success,
warning text and no resend after later recovery. Validate all public contracts
and malformed persisted values; run full suite with 100% statement/branch
coverage, CI, multiarch build, backup, managed update and live post-update cycle.

Readiness: implementation-ready. Scope, API, validation, baseline semantics,
single-writer assumption and unavoidable external delivery boundary reviewed.
