# Package Structure

This document defines the long-term package organization of Price Watch.

Every new package should follow the same structure.

---

# Core

```
core/

    domain/
    provider/
    rules/
    notifications/
    scheduler/
```

Core contains only business logic.

---

# Infrastructure

```
infrastructure/

    providers/
        alza/
        datart/
        amazon/
        lidl/

    notifications/
        email/
        telegram/
        discord/

    persistence/

    http/
```

Infrastructure performs all side effects.

---

# Applications

```
applications/

    cli/

    api/

    homeassistant/
```

Applications wire the system together.

---

# Tests

```
tests/

    unit/

        domain/

        provider/

        rules/

        notifications/

    integration/
```

Unit tests never require network access.

Integration tests may access external systems.

---

# Dependency Rules

Applications → Infrastructure → Core

Never the opposite.

---

# Public API

Every package exports its public API through:

__init__.py

Internal modules remain private.

---

# Naming

Packages use:

lowercase

Classes use:

PascalCase

Functions:

snake_case

Constants:

UPPER_CASE