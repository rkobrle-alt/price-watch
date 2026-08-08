# Rule Engine Public API

## Public Package

core.rules

---

## Public Classes

RuleEngine

EvaluationResult

RuleEvaluator

EvaluatorRegistry

RuleError

PriceReferencePolicy

---

## RuleEngine

Methods

evaluate(
    rule: Rule,
    previous: Product | None,
    current: Product,
    timestamp: datetime
) -> EvaluationResult

The timestamp is supplied by the caller.

---

## EvaluationResult

Immutable.

Fields

- matched
- reason
- timestamp

---

## RuleEvaluator

Protocol.

supports(rule)

evaluate(...)

---

## EvaluatorRegistry

register()

unregister()

get()

list()

---

## RuleError

Base exception.

Raised for:

- duplicate registration
- missing evaluator
- invalid evaluator

---

## PriceReferencePolicy

Deterministic method:

```python
enrich(
    current: Product,
    history: tuple[StateSnapshot, ...],
) -> Product
```

The caller supplies already loaded history. The policy performs no I/O.
