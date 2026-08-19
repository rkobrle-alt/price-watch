# STORY-032: Stable Public Release

## Objective

Implement ADR-0033 and release Price Watch 1.0.0 without changing the verified
runtime behavior of 0.31.0.

## Scope

- document the stable 1.x compatibility surface;
- make release-version agreement an automated test;
- enforce complete layer dependency direction with one repository-wide test;
- update runtime, Python package and Home Assistant release identity to 1.0.0;
- update operator and project release documentation;
- publish and verify the managed Home Assistant release.

Do not change Domain objects, Core business logic, Provider behavior, rule
evaluation, catalog discovery, discount qualification, email content,
scheduling, persistence schemas, App options, entities or permissions.

## Architecture

No package or dependency direction changes. The architecture test parses
Python imports without importing production modules and enforces:

- `core.domain` may import only itself and the Python standard library;
- all other Core packages may import Core and the standard library, never an
  outer layer;
- Infrastructure may import Infrastructure, Core and the standard library,
  never Applications;
- reusable Application packages may import Applications and Core, never
  Infrastructure;
- `applications.cli` and `applications.homeassistant` remain permitted outer
  composition roots.

## Public API

No public API changes. `applications.version.VERSION`, `pyproject.toml` and
`homeassistant/price_watch/config.yaml` must all contain `1.0.0`.

## Files

Create:

- `docs/adr/ADR-0033-stable-release-compatibility.md`;
- `docs/architecture/versioning-and-compatibility.md`;
- `docs/stories/STORY-032-stable-release.md`;
- `tests/unit/architecture/test_layer_dependencies.py`.

Modify only release metadata, affected roadmap/architecture/operator documents
and release-integrity tests. Production modules other than the canonical
version constant remain unchanged.

## Validation

The dependency test parses the real production source tree and uses focused
pure helper assertions for prohibited directions. It never imports production
modules, mutates the repository or accesses the network.

The packaging test parses and compares the runtime, project and App manifest
versions rather than relying on independent release literals.

## Tests

- repository-wide production import scan;
- prohibited Domain, Core, Infrastructure and reusable-Application examples;
- permitted composition-root examples;
- exact version agreement at `1.0.0`;
- existing full unit and integration suite;
- 100 percent statement and branch coverage.

No test accesses the network or is skipped.

## Acceptance Criteria

- ADR-0033 and compatibility documentation are internally consistent;
- no runtime behavior or public API changes from 0.31.0;
- dependency-direction and release-version gates pass;
- all tests pass with 100 percent statement and branch coverage;
- Git working tree is clean after logical commits;
- tag `v1.0.0` is published and both GitHub workflows succeed;
- the managed Home Assistant App reports installed version 1.0.0;
- the first post-update catalog cycle reports healthy version 1.0.0 states;
- no TODO, placeholder, pass statement, skipped test, commented code or dead
  code is introduced.

## Readiness Review

Specification is implementation-ready.
