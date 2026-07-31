# EPIC-001

## Product Synchronization

Goal:

Synchronize product information from external providers.

Workflow:

Provider

↓

State Store

↓

Rule Engine

↓

Notification


The workflow depends on the `core.state.StateStore` abstraction.

Concrete State Store implementations are supplied by Infrastructure.

Local durable synchronization uses
`infrastructure.persistence.json.JsonStateStore`.

Product snapshots are keyed by `snapshot.product.id`.

Reusable orchestration belongs to `applications.synchronization` and follows
ADR-0009. Notifications are delivered before the corresponding current
snapshot is stored.

The first user-facing composition is `applications.cli sync` according to
ADR-0010.

Repeated execution is provided by `applications.scheduler` and the
`applications.cli watch` composition according to ADR-0011. Scheduled cycles
run serially and reuse the same durable workflow composition.

Repeatable startup configuration is supplied by the versioned TOML contract in
ADR-0012. Configuration loading does not introduce another workflow path.

Done when:

- Products are retrieved.
- Previous state is loaded.
- Rules are evaluated.
- Notifications are generated and delivered.
- Current state is stored.
- The same workflow can be executed repeatedly without overlapping cycles.
