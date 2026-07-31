# ADR-0007: Lidl Parkside Provider

## Status

Accepted

---

## Context

The platform requires its first real product provider.

Lidl Czech Republic publishes Parkside product details as schema.org
`Product` and `Offer` JSON-LD on individual product pages. Its robots policy
disallows automated use of search and pagination endpoints.

The provider must therefore retrieve useful product data without coupling Core
to HTTP or relying on catalog crawling.

---

## Decision

The first provider monitors an explicit, application-supplied collection of
Lidl Czech Republic product URLs for Parkside tools.

The implementation belongs to:

```text
infrastructure.providers.lidl
```

It implements the existing `core.provider.Provider` contract without changing
the Provider SDK or Domain.

The provider:

- accepts only HTTPS product URLs hosted by `lidl.cz` or `www.lidl.cz`
- does not discover products, query search endpoints or paginate catalogs
- reads schema.org `Product` and `Offer` JSON-LD
- accepts brands whose name begins with `PARKSIDE`, case-insensitively
- converts supported data into immutable Domain `Product` objects
- reports an individual retrieval or conversion failure as a `ProviderError`
  in `FetchResult.errors`
- continues processing the remaining configured URLs after an individual
  failure

---

## Identity

The provider uses one stable UUID-based `ProviderId`.

Each product uses a deterministic UUIDv5 `ProductId` derived from the provider
identifier and Lidl SKU. The same Lidl SKU therefore retains the same Domain
identity across synchronization cycles.

Identifiers are generated in Infrastructure, not Core.

---

## HTTP Boundary

The provider depends on an injected `TextHttpClient` Protocol from:

```text
infrastructure.http
```

The reference `UrllibTextHttpClient` implementation uses the Python standard
library. It raises `HttpClientError` for operational retrieval and decoding
failures.

Applications will compose the concrete HTTP client, clock and product URLs.
Unit tests inject fakes and never use the network.

---

## Time

The provider receives an injected callable clock.

The cycle start timestamp is used as `Product.created_at`. The cycle finish
timestamp and elapsed duration are recorded in `FetchResult`.

Both timestamps must be timezone-aware. The Core does not read the clock.

---

## Data Mapping

JSON-LD fields map as follows:

| JSON-LD | Domain |
| --- | --- |
| `sku` | deterministic `Product.id` input |
| `brand.name` | `Product.brand` |
| `name` | `Product.name` |
| `offers.price` | `Product.current_price.amount` |
| `offers.priceCurrency` | `Product.current_price.currency` |
| `offers.availability` | `Product.availability` |
| first `image` | `Product.image_url` |
| configured URL | `Product.url` |

The first version sets `original_price` to `None` and `discount_percent` to
zero because the selected structured source does not provide a reliable
original-price field.

Unsupported currency, missing required structured data, unknown availability
or a non-Parkside brand is a conversion failure for that product.

---

## Error Handling

Invalid public argument types raise `TypeError`.

Invalid configuration values raise `ValueError`.

HTTP operational failures raise `HttpClientError` at the HTTP boundary and
are converted to per-product `ProviderError` values by the provider.

Unexpected programming errors are not silently converted.

---

## Alternatives Considered

### Crawl Lidl search results

Rejected because it conflicts with the published robots policy and would make
the provider depend on unstable discovery and pagination behavior.

### Put HTTP abstractions in Core

Rejected because HTTP is an Infrastructure concern and the Provider contract
already exposes only Domain products to Core.

### Use page-specific HTML selectors

Rejected for the first version because published JSON-LD is a smaller and more
stable integration surface.

---

## Consequences

Advantages:

- respects existing Provider and Clean Architecture boundaries
- deterministic product identities
- no catalog crawling
- network-free unit testing
- partial failures do not discard successful products

Costs:

- applications must explicitly configure product URLs
- page schema changes may require an Infrastructure-only parser update
- adding product discovery requires a separate future decision

