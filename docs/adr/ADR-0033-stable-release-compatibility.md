# ADR-0033: Stable 1.x Compatibility Policy

## Status

Accepted

## Context

Price Watch has completed the Domain, Provider SDK, Rule Engine, persistence,
CLI, Home Assistant catalog monitoring, daily digest, maintenance and
operational-health milestones. Version 0.31.0 has also been accepted in real
operation: the managed App upgraded successfully and the new/existing discount
sections were delivered as specified.

The roadmap identifies the next milestone as 1.0.0 but does not define what
"stable" protects. Without an explicit boundary, ordinary 1.x maintenance
could accidentally rename exports, reject existing App options, change entity
contracts or strand a valid SQLite database.

## Decision

Price Watch follows Semantic Versioning from 1.0.0. The current behavior and
contracts at 0.31.0 form the 1.0 compatibility baseline. Version 1.0.0 changes
release identity and documentation only; it does not change monitoring,
qualification, persistence, scheduling, delivery or Home Assistant behavior.

Within the 1.x series:

- exported names in package `__init__.py` files are not removed or renamed;
- existing public call forms, return types and documented exception boundaries
  remain valid;
- new public parameters are optional and appended where practical;
- existing CLI commands, accepted options and documented exit meanings remain
  valid;
- existing Home Assistant App options retain their meaning and defaults for
  previously valid option documents;
- existing entity IDs, state types and documented attribute names are not
  removed, renamed or assigned incompatible meanings;
- valid SQLite schema versions 1 through 6 continue to migrate sequentially
  and transactionally to the current schema without silent data loss;
- explicit-mode JSON schema 1 and application-configuration schema 1 remain
  readable until an approved migration or compatibility decision replaces
  them.

Backward-compatible additions remain possible in 1.x when specified by an ADR
and STORY. An intentional incompatible change requires an ADR, migration and a
new major version. Security or upstream-provider emergency fixes may narrow
unsafe external input, but the exception and migration impact must be stated
explicitly before release.

User-visible notification wording is not a machine-readable API. It may evolve
through an approved STORY, while notification count, reservation and delivery
semantics remain protected contracts.

Lidl markup, availability and network service are external dependencies and
are not covered by a compatibility guarantee. Their failures remain observable
through the established provider and operational-health boundaries.

## Release Integrity

`applications.version.VERSION` remains the runtime version authority.
`pyproject.toml` and the Home Assistant App manifest carry the same release
value. Automated tests reject disagreement between these three locations.

A stable release requires:

- a clean repository and reviewed logical commits;
- the complete test suite with 100 percent statement and branch coverage;
- automated dependency-direction checks;
- matching runtime, package and Home Assistant versions;
- a `v<version>` Git tag built by the existing tag-only multiarchitecture
  publication workflow;
- successful managed-App update and healthy post-update cycle.

## Public API

No Python, CLI, persistence or Home Assistant public API is added or changed by
this decision. This ADR defines compatibility expectations for existing APIs.

## Dependency Direction

The established direction is unchanged:

```text
Applications --> Infrastructure --> Core --> Domain
```

Composition roots may construct Infrastructure. Reusable Application
workflows depend only on Core contracts. Infrastructure never imports
Applications, and Core never imports either outer layer.

## Alternatives Considered

### Continue 0.x feature releases indefinitely

Rejected because deployed behavior is already complete and proven, while the
absence of a stability contract makes future maintenance less predictable.

### Redesign before 1.0

Rejected because no architectural defect currently prevents the primary use
case. A speculative rewrite would add migration risk without user value.

### Freeze every output byte

Rejected because human-readable messages and documentation must remain
improvable. Compatibility protects programmatic and durable contracts rather
than incidental presentation details.

## Consequences

Users receive a clear long-term compatibility promise. Future work must
distinguish additive 1.x changes from major-version changes. The release adds
no runtime complexity and preserves the verified 0.31.0 behavior exactly.
