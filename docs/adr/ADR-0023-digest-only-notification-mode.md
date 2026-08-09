# ADR-0023: Digest-Only Catalog Notification Mode

## Status

Accepted

---

## Context

Catalog monitoring currently sends two kinds of email through the configured
Home Assistant notify entity:

- an individual alert when a product first reaches a qualifying price or
  returns to stock;
- one optional daily digest containing all currently qualifying discounts.

Durable reservations prevent repeated delivery of the same individual price,
but a catalog containing several newly qualifying products still produces one
email per product. The operator requires a quieter mode in which monitoring,
history, discount calculation and the daily digest continue while all
individual alerts are disabled.

The discount threshold cannot be removed to achieve this result because the
daily digest and catalog status both require it. Delivery policy therefore
needs an explicit Home Assistant catalog option.

---

## Decision

Add the optional Home Assistant App option:

```text
individual_notifications_enabled: bool
```

It is valid only in catalog mode. Option documents that omit it retain the
existing value `true` for backward compatibility. The packaged default for new
installations is `false`, making one daily digest the default notification
experience.

When the value is `false`:

- catalog discovery, bounded refresh and observation persistence continue;
- reference-price enrichment and catalog discount statistics continue;
- the configured price threshold continues to select daily-digest products;
- the catalog synchronization workflow receives no individual rules;
- no price-drop or back-in-stock `Notification` is generated or delivered;
- no individual notification reservation is created;
- daily digest delivery is unchanged.

When the value is `true`, existing catalog behavior is unchanged. Explicit URL
mode and the CLI are unchanged.

The option is represented by the immutable `HomeAssistantConfig` field:

```python
individual_notifications_enabled: bool = True
```

Invalid types raise `TypeError`. A false value without catalog monitoring is
invalid. Strict option parsing rejects the option in explicit mode.

---

## Architecture

The decision is an Application composition policy. It does not change Core,
Domain, Provider SDK, Rule Engine, notification Protocols or Infrastructure.
The existing synchronization workflow remains responsible for processing any
rules supplied by its caller; Home Assistant catalog composition supplies an
empty rule tuple in digest-only mode.

```text
Home Assistant catalog options
    |
    +--> individual notifications enabled --> price and stock rules
    |
    +--> individual notifications disabled --> no individual rules
    |
    +--> daily digest enabled -------------> daily digest workflow
```

The two choices are independent. Disabling individual notifications does not
implicitly enable the digest; operators may intentionally configure no email
delivery.

---

## Consequences

Advantages:

- all qualifying products can arrive in one predictable daily email;
- no Core or persistence contract changes;
- existing installations remain backward compatible;
- monitoring and dashboard diagnostics continue without email noise.

Costs:

- digest-only users learn about a new discount at the configured daily time,
  not immediately;
- one additional App option must be documented and tested.
