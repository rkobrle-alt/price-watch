# Rule Engine Architecture

## Purpose

The Rule Engine evaluates business rules against product changes.

The engine is deterministic, stateless and free of side effects.

---

# Public API

```
RuleEngine
```

Public method:

```
evaluate(
    rule: Rule,
    previous: Product | None,
    current: Product,
    timestamp: datetime
) -> EvaluationResult
```

---

# Internal Structure

```
RuleEngine
     │
     ▼
EvaluatorRegistry
     │
     ├──────────────┐
     ▼              ▼
PriceDropEvaluator  BackInStockEvaluator
     │              │
     └──────┬───────┘
            ▼
     EvaluationResult
```

---

# Responsibilities

## RuleEngine

Coordinates evaluation.

Contains no business rules.

---

## EvaluatorRegistry

Maps RuleType to evaluator.

Responsible only for lookup.

---

## RuleEvaluator

Abstract protocol.

```
supports(rule)

evaluate(...)
```

---

## EvaluationResult

Immutable value object.

Contains:

- matched
- reason
- timestamp

---

# Dependency Rules

RuleEngine depends on:

- Domain
- Evaluators

Evaluators depend only on:

- Domain

The Rule Engine does not depend on Notification.

The Rule Engine does not depend on Provider SDK.

---

# Extensibility

Adding a new rule requires:

1. Implement evaluator.
2. Register evaluator.

Nothing else changes.