# Versioning and Compatibility

Price Watch uses Semantic Versioning from version 1.0.0 according to ADR-0033.

## Stable Contracts

The stable 1.x surface consists of:

- names exported by public package `__init__.py` files;
- documented public Python call forms, values and exception boundaries;
- CLI commands, accepted options and exit meanings;
- valid Home Assistant App option documents;
- published Home Assistant entity IDs, state types and attribute meanings;
- sequential SQLite migration from valid schemas 1 through 6;
- JSON state schema 1 and application configuration schema 1.

Compatible additions may introduce new optional APIs, options or entities.
Removing, renaming or incompatibly redefining a stable contract requires an
approved ADR, a migration where data is involved and a new major version.

Human-readable notification wording may change through an approved STORY.
Delivery count, reservation behavior and persistence semantics remain stable.

## Release Identity

The runtime authority is `applications.version.VERSION`. The same value is
repeated in `pyproject.toml` and `homeassistant/price_watch/config.yaml` for
their respective packaging tools. Tests require all three values to match.

Release tags use `v<major>.<minor>.<patch>`. Tag publication builds the
existing amd64/aarch64 Home Assistant image. A release is complete only after
CI, image publication, managed-App update and one healthy post-update cycle.

## Architecture Gate

Automated tests enforce these dependency rules across the complete source
tree:

- Domain imports no other Core subsystem or outer layer;
- Core imports neither Infrastructure nor Applications;
- Infrastructure imports no Application package;
- reusable Application workflows import no Infrastructure implementation;
- CLI and Home Assistant remain the concrete outer composition roots.

These checks complement, rather than replace, ADR and public-API review.
