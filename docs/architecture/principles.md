# Architecture Principles

These principles apply to the entire Price Watch project.

They take precedence over implementation convenience.

---

# 1. Clean Architecture

Dependencies always point inward.

```
Applications
      │
Infrastructure
      │
Core
      │
Domain
```

The Domain layer must not depend on any outer layer.

---

# 2. Immutable Domain

Domain entities and value objects are immutable.

Mutable state is not allowed inside the Domain.

---

# 3. Explicit Public API

Every package exports its public API through `__init__.py`.

Internal modules are not part of the public contract.

---

# 4. Protocols for Contracts

Service contracts use `typing.Protocol`.

Avoid inheritance unless shared implementation is required.

---

# 5. Single Responsibility

Every class has exactly one responsibility.

If a class has multiple independent reasons to change, split it.

---

# 6. Open/Closed Principle

New functionality should be added by extension.

Existing implementation should rarely require modification.

Examples:

- New Provider
- New Rule Evaluator
- New Notification Channel

---

# 7. No Circular Dependencies

Circular imports are forbidden.

Dependencies must form a directed acyclic graph.

---

# 8. Composition over Inheritance

Prefer composition.

Inheritance is used only when there is a genuine "is-a" relationship.

---

# 9. Deterministic Core

The Core must be deterministic.

Core must not:

- read the system clock
- perform network requests
- access databases
- access the filesystem
- depend on environment variables

Required external values are supplied by callers.

---

# 10. Side Effects at the Edge

Only Infrastructure may perform side effects.

Examples:

- HTTP
- File IO
- Notifications
- Home Assistant
- Databases

Core contains business logic only.

---

# 11. Testability

Every Core component must be unit testable.

Business logic must not require external services.

---

# 12. Backward Compatibility

Public APIs should remain stable whenever practical.

Breaking changes require an ADR.

---

# 13. Error Handling

Each subsystem defines its own exception hierarchy.

Examples:

- ProviderError
- RuleError

Exceptions must carry meaningful information.

---

# 14. Documentation First

Architecture changes begin with an ADR.

Implementation begins only after the ADR is accepted.

Stories define implementation work.

---

# 15. Code Quality

Every contribution must:

- pass all tests
- maintain or improve coverage
- contain no TODO placeholders
- contain no `pass` implementations
- avoid dead code
- use explicit typing

---

# Definition of Done

A feature is complete only when:

- ADR (if required) is accepted
- Story is implemented
- Unit tests pass
- Coverage target is met
- Architecture review is approved
- Code is committed
- Version tag is created when appropriate