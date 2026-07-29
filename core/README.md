# Core

The core package contains the platform's application-independent domain model.
It has no dependencies on infrastructure or client applications.

## Domain API

The public API is exported by `core.domain`:

- Entities: `Product`, `Provider`, `PriceRecord`, `Rule`, and `Notification`
- Value objects: `Money`, `Percentage`, `ProductId`, and `ProviderId`
- Enums: `Currency`, `ProviderStatus`, and `RuleType`
- Exceptions: `DomainError` and `ValidationError`

All entities and value objects are immutable. Prices use `Decimal`, identifiers
use `UUID`, and domain timestamps must be timezone-aware.

`Product.availability` records whether a product can currently be purchased and
defaults to `True` for compatibility. `Rule.rule_type` selects the future rule
evaluator, while `Rule.parameters` stores an immutable, opaque configuration
mapping.

## Provider SDK

The transport-neutral provider integration API is exported by `core.provider`:

- `Provider`: structural provider contract
- `ProviderMetadata`: immutable provider description
- `FetchResult`: immutable products, timing, and errors from a fetch
- `ProviderError`: base provider failure
- `ProviderRegistry`: instance-local provider registration

Concrete providers belong outside Core and translate external data into domain
`Product` entities before returning it through this API.
