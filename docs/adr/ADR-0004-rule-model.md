# ADR-0004: Rule Model

## Status

Accepted

---

## Context

The Rule Engine requires additional domain information that is not present in the initial domain model.

Rules must expose their type.

Products must expose whether they are available.

The Rule Engine must remain deterministic.

---

## Decision

The domain model is extended with rule classification and product availability.

The Rule Engine will consume only immutable domain objects.

---

## Rule

Rule SHALL contain:

- id
- name
- enabled
- rule_type
- parameters

`rule_type` identifies the evaluator responsible for processing the rule.

`parameters` stores rule-specific configuration.

Initially it is an immutable mapping.

---

## Product

Product SHALL expose:

- availability

Availability is represented as a boolean.

Future versions may replace it with a richer stock model without changing the Rule Engine API.

---

## Rule Parameters

Different rule types require different configuration.

Examples:

PRICE_DROP

- percentage
- fixed_amount

BACK_IN_STOCK

- no parameters

The engine treats parameters as opaque data.

Only evaluators interpret them.

---

## Deterministic Evaluation

The Rule Engine must never read the system clock.

Evaluation timestamps are supplied by the caller.

---

## RuleError

All Rule Engine exceptions derive from RuleError.

RuleError belongs to the Rule Engine package.

---

## Disabled Rules

Disabled rules are never evaluated.

The Rule Engine returns a non-matching EvaluationResult explaining that the rule is disabled.