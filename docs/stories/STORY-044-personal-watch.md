# STORY-044: Personal daily watch configuration

Implement ADR-0040 across Core preference models/policy, Lidl URL resolver,
pure HA option parsing/schema/translations, optional catalog seeds, freshness,
selection/formatting, price-history and baseline/delivery composition.

Acceptance: favorites/targets without sale reference, exact inclusive target
boundary, currency mismatch, stale/future/absent pages, hidden precedence,
category OR/fallback and normalized phrase matching. Preserve inactive defaults.
Test stable identity across changed slug/tracking links, duplicate validation,
unknown watched products seeded once without overwriting canonical URLs, and
explicit-watch priority without exceeding the 200-product refresh budget.
Real SQLite integration verifies nonsale watch→sale novelty, filtering, history,
banner fallback, preparation compensation, restart and duplicate protection.
Validate manifest defaults and category settings, run full suite with 100%
statement/branch coverage, CI, multiarch publication, backup and live App cycle.

Readiness: implementation-ready. User controls, identity, overrides, target
freshness, baseline meaning and backwards-compatible defaults reviewed.
