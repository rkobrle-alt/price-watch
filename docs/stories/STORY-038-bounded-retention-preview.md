# STORY-038: Bounded-memory retention preview

## Context and evidence

On 2026-11-11 the last completed storage publication was at 03:17:34
Europe/Prague with 435,665 observations. The corresponding retention preview
and cycle completion were absent. Restart restored monitoring and digest
delivery. The interrupted process stack was not captured, so the exact cause
of the prolonged stall is not proven.

The existing retention selector materializes all raw SQLite rows and all
decoded domain snapshots simultaneously, plus multiple per-observation sets.
This is a reproducible, history-dependent memory amplification in the stage
where progress stopped. Correct this implementation without changing ADR-0025
or ADR-0026 semantics.

## Scope and API

- Change only the private SQLite retention selection implementation.
- Keep every public signature and export unchanged.
- Iterate the ordered SQLite cursor and validate each complete snapshot.
- For preview, retain counts and latest/highest-price guards only; memory
  must scale with distinct products/currencies rather than observation count.
- For explicit apply, additionally retain candidate old sequence identifiers,
  not snapshots. Keep the complete pre-deletion backup and transaction.
- Preserve cutoff inclusivity, insertion-based latest state, earliest tied
  Decimal maximum per product/currency, and all existing error boundaries.
- Do not delete history automatically, change cadence, skip corrupt rows,
  migrate the database, change notifications or modify Core.

## Verification and acceptance

- A real SQLite preview regression with thousands of same-product observations
  must fail the bounded-memory assertion before the fix and pass afterward.
- Cover all-old and all-recent histories, exact counts, protected ties,
  out-of-order timestamps, multiple currencies and read-only preview behavior.
- Existing backup, apply, rollback, validation and corruption tests must pass.
- Run the complete suite with 100% statement and branch coverage.
- Record measured before/after memory results; do not claim that this proves
  every possible production stall has been eliminated.

Readiness: implementation-ready; no public or architectural decision changes.

## Local verification measurements

Python 3.14, real SQLite, synthetic single-product history, `tracemalloc`
started only around `plan()` (not database setup):

- Before: 8,000 all-old rows peaked at 19,023,564 Python-allocated bytes;
  all-recent rows at 19,329,346. Both failed the 4 MiB regression bound.
- After: 8,000 all-old rows peaked at 12,083 bytes (0.750 seconds);
  80,000 at 11,587 bytes (7.024 seconds).

These are local Python allocation measurements, not production RSS or a
guarantee of cycle duration. Snapshot decoding remains linear in history size.
The production history showed prior previews taking roughly 158 seconds;
this change removes memory amplification, not all costs of full validation.
No production data was deleted and no release was deployed by these tests.
