# STORY-003: Rule Engine

## Goal

Implement the Rule Engine according to:

- ADR-0003 Rule Engine
- ADR-0004 Rule Model
- Architecture Principles
- Package Structure
- Rule Engine Public API

The Rule Engine evaluates business rules without side effects.

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
- exceptions.py

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
- RuleError

---

## RuleError

Create RuleError as the base exception for the Rule Engine.

Raise RuleError for:

- duplicate evaluator registration
- unknown RuleType
- invalid evaluator registration

---

## RuleEvaluator

Use typing.Protocol.

Each evaluator exposes exactly one supported RuleType.

Required members:

rule_type: RuleType

evaluate(
    rule: Rule,
    previous: Product | None,
    current: Product,
    timestamp: datetime,
) -> EvaluationResult

---

## EvaluationResult

Frozen dataclass.

Fields:

- matched: bool
- reason: str
- timestamp: datetime

Timestamp is supplied by the caller.

EvaluationResult is immutable.

---

## EvaluatorRegistry

Responsibilities:

- register()
- unregister()
- get()
- list()

The registry maps:

RuleType → RuleEvaluator

Duplicate registrations raise RuleError.

Unknown RuleType raises RuleError.

---

## RuleEngine

Public method:

evaluate(
    rule: Rule,
    previous: Product | None,
    current: Product,
    timestamp: datetime,
) -> EvaluationResult

Behavior:

- disabled rules return a non-matching EvaluationResult
- RuleEngine contains no business logic
- RuleEngine delegates evaluation to the registered evaluator

Dispatch occurs only through EvaluatorRegistry.

---

## PriceDropEvaluator

Supports:

RuleType.PRICE_DROP

Behavior:

Compare previous and current prices.

Return EvaluationResult.

Interpret rule.parameters.

---

## BackInStockEvaluator

Supports:

RuleType.BACK_IN_STOCK

Behavior:

Detect transition:

availability == False

↓

availability == True

Return EvaluationResult.

---

## Forbidden

RuleEngine MUST NOT:

- compare prices
- inspect availability
- use if/elif chains based on RuleType
- call datetime.now()
- perform network requests
- access databases

---

## Dependencies

Allowed:

- Domain
- Standard Library

Forbidden:

- Provider implementations
- HTTP
- Databases
- Home Assistant

---

## Tests

Provide complete unit tests.

Cover:

- evaluator registry
- duplicate registration
- unknown RuleType
- disabled rules
- engine dispatch
- price drop
- back in stock
- immutable EvaluationResult
- public exports

Target:

100% coverage.