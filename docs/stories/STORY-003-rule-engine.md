# STORY-003: Rule Engine

## Goal

Implement the Rule Engine according to ADR-0003 and the Rule Engine architecture document.

The engine evaluates business rules without side effects.

---

## Package Structure

Create:

core/rules/

with:

- __init__.py
- engine.py
- registry.py
- evaluation.py
- evaluator.py

Create:

core/rules/evaluators/

with:

- __init__.py
- price_drop.py
- back_in_stock.py

---

## Public API

Export through:

core.rules

Public classes:

- RuleEngine
- EvaluationResult
- RuleEvaluator
- EvaluatorRegistry

---

## RuleEvaluator

Use typing.Protocol.

Required methods:

supports(rule: Rule) -> bool

evaluate(
    rule: Rule,
    previous: Product | None,
    current: Product
) -> EvaluationResult

---

## EvaluationResult

Frozen dataclass.

Fields:

- matched: bool
- reason: str
- timestamp: datetime

Timestamp must be timezone-aware.

---

## EvaluatorRegistry

Responsibilities:

- register()
- unregister()
- get()

Duplicate registrations raise RuleError.

Unknown RuleType raises RuleError.

---

## RuleEngine

Public method:

evaluate(
    rule,
    previous,
    current
)

The engine MUST NOT contain business logic.

It only selects the proper evaluator.

---

## PriceDropEvaluator

Supports:

RuleType.PRICE_DROP

Compare previous and current price.

Return EvaluationResult.

---

## BackInStockEvaluator

Supports:

RuleType.BACK_IN_STOCK

Detect transition:

Unavailable → Available

Return EvaluationResult.

---

## Design Rules

Forbidden:

if rule.type == ...

inside RuleEngine.

Dispatch must occur through EvaluatorRegistry.

---

## Dependencies

Allowed:

Core Domain

Forbidden:

Provider SDK internals
HTTP
Database
Home Assistant

---

## Tests

Provide complete unit tests.

Test:

- registry
- duplicate registration
- unknown rule
- engine dispatch
- price drop
- back in stock
- public exports
- immutability

Target:

100% coverage.