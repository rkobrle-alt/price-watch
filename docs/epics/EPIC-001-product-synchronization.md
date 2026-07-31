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

Done when:

- Products are retrieved.
- Previous state is loaded.
- Rules are evaluated.
- Notifications are generated and delivered.
- Current state is stored.
