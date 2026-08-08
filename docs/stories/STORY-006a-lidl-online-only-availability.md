# STORY-006a: Lidl Online-Only Availability

## Goal

Accept Lidl Czech Republic products whose schema.org `Offer.availability` is
`OnlineOnly` without changing the Domain, Provider SDK or provider public API.

---

## Scope

Extend only the Lidl JSON-LD translation in:

```text
infrastructure.providers.lidl
```

The value is accepted with or without a schema.org URL prefix and maps to
`Product.availability=True` because the product can currently be purchased
online.

The existing mappings remain unchanged:

- `InStock` maps to `True`
- `OutOfStock` maps to `False`
- `SoldOut` maps to `False`

All other availability values remain conversion failures represented by a
per-product `ProviderError` at the provider boundary.

---

## Public API

No public API changes.

`LidlParksideProvider`, the Domain model and the Provider SDK retain their
existing contracts and exports.

---

## Dependency Boundaries

- Core and Domain files must not be modified.
- Applications, persistence, rules and notifications must not be imported.
- The mapping remains an Infrastructure concern.
- No new runtime dependency is introduced.

---

## Tests

Network-free unit tests must prove:

- bare `OnlineOnly` maps to `True`;
- schema.org URL-prefixed `OnlineOnly` maps to `True`;
- existing availability mappings remain unchanged;
- an unsupported value still produces the existing conversion failure.

The complete test suite must retain 100% statement and branch coverage.

---

## Acceptance Criteria

- Lidl products marked `OnlineOnly` are returned as available products.
- The mapping works with and without a schema.org URL prefix.
- Unknown availability values are still rejected.
- No Domain, Provider SDK or public API is changed.
- Core remains deterministic and Infrastructure-independent.
- No TODOs, placeholders, skipped tests or dead code are introduced.
- All tests pass with 100% statement and branch coverage.
