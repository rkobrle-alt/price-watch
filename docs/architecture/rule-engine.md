# Rule Engine Architecture

## Purpose

The Rule Engine evaluates business rules against product changes.

The engine is deterministic, stateless and free of side effects.

ADR-0019 adds the independent deterministic `PriceReferencePolicy`. It
enriches an immutable current product from caller-supplied history before the
unchanged engine API is invoked.

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

## PriceReferencePolicy

Selects the current provider original price or the highest prior
same-currency observation and returns an immutable product enriched with that
reference and exact discount percentage. It performs no history access itself.

`PriceDropEvaluator` prefers the enriched current original price and supports
the optional `available_only` boolean rule parameter. Without enrichment or
that parameter it preserves previous-state behavior.

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
