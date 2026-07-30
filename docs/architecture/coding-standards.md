# Coding Standards

These standards apply to all production code.

---

# Python Version

Python 3.13+

---

# Typing

Public APIs must use explicit type hints.

Avoid Any whenever practical.

Prefer Protocol over ABC unless shared implementation is required.

---

# Dataclasses

Use:

- frozen=True
- slots=True

when appropriate.

---

# Imports

Prefer absolute imports.

Avoid circular imports.

No wildcard imports.

---

# Exceptions

Every subsystem owns its own exception hierarchy.

Exceptions should communicate domain intent.

---

# Logging

Core never logs.

Applications and Infrastructure may log.

---

# Time

Core never reads the system clock.

Time is injected.

---

# Randomness

Core never generates random values except where explicitly required.

Identifiers are created at the application boundary.

---

# Side Effects

Only Infrastructure performs:

- HTTP
- Files
- Databases
- Notifications

---

# Testing

Every new public API requires tests.

Regression tests are added for every bug fix.

---

# Documentation

Public classes require docstrings.

Complex business rules require explanatory comments.

Do not comment obvious code.

---

# Performance

Optimize only after correctness.

Prefer readability over micro-optimizations.

---

# Review Checklist

Before merging:

- tests pass
- coverage maintained
- no TODO
- no pass
- no dead code
- public API reviewed
- architecture respected