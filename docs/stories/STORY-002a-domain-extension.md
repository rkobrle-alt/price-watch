# STORY-002a: Domain Extension for Rule Engine

## Goal

Extend the existing immutable domain model according to ADR-0004.

This story only updates the domain model.

No Rule Engine implementation is part of this story.

---

## Rule

Extend Rule with:

- rule_type
- parameters

### rule_type

Type:

RuleType

Mandatory.

---

### parameters

Type:

Mapping[str, Any]

Immutable.

Default:

empty mapping

The domain model stores parameters but never interprets them.

---

## Product

Extend Product with:

- availability

Type:

bool

Default:

True

---

## Immutability

The existing immutable design must remain unchanged.

No mutable collections.

---

## Public API

Update exports if necessary.

No breaking changes.

---

## Validation

Rule must reject:

- missing RuleType

Product availability is always required.

---

## Compatibility

Existing tests must continue to pass.

Add new tests only for:

- rule_type
- parameters
- availability
- immutability
- public exports

Target:

100% coverage.