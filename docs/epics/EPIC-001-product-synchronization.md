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

Product snapshots are keyed by `snapshot.product.id`.

Done when:

- Products are retrieved.
- Previous state is loaded.
- Rules are evaluated.
- Notifications are generated and delivered.
- Current state is stored.