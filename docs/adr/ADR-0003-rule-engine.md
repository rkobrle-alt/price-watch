# ADR-0003: Rule Engine

## Status

Accepted

---

## Context

The Rule Engine evaluates user-defined conditions against product data.

It is responsible for determining whether a notification should be generated.

The Rule Engine contains business logic only.

It must not know how products were retrieved or how notifications are delivered.

---

## Decision

The Rule Engine shall evaluate immutable Rule objects against immutable Product objects.

Evaluation produces immutable EvaluationResult objects.

The engine has no side effects.

---

## Responsibilities

The Rule Engine SHALL:

- evaluate rules
- compare current and previous product state
- determine whether a rule matches
- provide an explanation of the result

The Rule Engine SHALL NOT:

- download products
- send notifications
- access databases
- access Home Assistant
- modify Product objects

---

## Supported Rule Types

Initially:

- PRICE_DROP
- BACK_IN_STOCK

Future rule types must be added without modifying existing evaluation logic.

---

## Design Principles

The engine must satisfy:

- Open/Closed Principle
- Single Responsibility Principle
- Dependency Inversion

Each rule type shall be evaluated by an independent evaluator.

---

## Dependency Diagram

Applications
    │
Notification
    │
Rule Engine
    │
Domain

Dependencies always point downward.

---

## Consequences

Advantages:

- Easy testing
- Extensible architecture
- Independent evaluators
- Predictable behavior

Disadvantages:

- More classes
- Additional abstraction

These costs are acceptable.