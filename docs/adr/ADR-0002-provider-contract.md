# ADR-0002: Provider Contract

## Status

Accepted

---

## Context

The Price Watch platform must support many different providers without changing the Core domain.

Examples include:

- Lidl
- Kaufland
- Alza
- Datart
- Amazon
- Notino

Every provider may use a completely different technology:

- REST API
- GraphQL
- HTML scraping
- RSS
- XML
- CSV
- local files

The Core domain must never depend on these technologies.

---

## Decision

Every provider must implement a common Provider contract.

The contract returns only domain objects.

Providers are responsible for translating external data into domain entities.

The Core domain never receives raw JSON, HTML, XML, CSV or API-specific objects.

---

## Responsibilities

A Provider SHALL:

- identify itself
- retrieve product data
- validate external data
- convert external data into Product entities
- report failures using ProviderError

A Provider SHALL NOT:

- store products
- execute business rules
- send notifications
- access Home Assistant
- access databases

---

## Dependency Rule

```
Applications
        │
Infrastructure (Providers)
        │
Core
```

Dependencies always point downward.

The Core layer must never import infrastructure code.

---

## Extensibility

Adding a new provider must require only:

- creating a new Provider implementation
- registering the provider

The Core domain must remain unchanged.

---

## Consequences

Advantages:

- Open/Closed Principle
- Easy testing
- Plugin architecture
- Independent providers
- Clean separation of responsibilities

Disadvantages:

- Slightly more abstraction
- Additional interfaces
- More initial design work

The long-term maintenance benefits outweigh these costs.