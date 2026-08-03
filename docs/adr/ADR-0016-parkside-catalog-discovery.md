# ADR-0016: Parkside Catalog Discovery

## Status

Accepted

---

## Context

Price Watch currently monitors only explicitly configured Lidl product URLs.
The product goal now requires automatic discovery of every Lidl Czech Republic
product belonging to the Parkside or Parkside Performance brand, including
tools, garden equipment, batteries, chargers, accessories and spare parts.

ADR-0007 intentionally rejected Lidl search and pagination endpoints because
the published robots policy disallows their automated use. That restriction
still applies. The current robots policy does, however, advertise the public
product sitemap at:

```text
https://www.lidl.cz/static/sitemap.xml
```

The advertised index identifies the Czech product sitemap. Catalog discovery
must use that published source without turning the existing product-page
provider into a crawler or moving provider-specific data into Domain.

---

## Decision

Catalog discovery is a separate Core contract with a Lidl Infrastructure
implementation. It does not change the existing `Provider` contract or
`LidlParksideProvider` behavior.

The Core package is:

```text
core.catalog
```

It contains only immutable `ProductReference` values, the `ProductCatalog`
Protocol and the `CatalogError` operational-failure contract.

The first implementation is:

```text
infrastructure.providers.lidl.LidlParksideCatalog
```

It reads the robots-advertised sitemap index and its Czech product sitemap,
then returns deterministic Parkside candidate references. It never calls Lidl
search, pagination, sorting, advisor or product-listing endpoints.

---

## Public Contracts

```python
@dataclass(frozen=True, slots=True)
class ProductReference:
    provider_id: ProviderId
    external_id: str
    url: str
```

`external_id` identifies the canonical Lidl product-page identifier such as
`p100382709`. It is a discovery identity, not a Domain `ProductId`. The
existing product provider continues deriving `ProductId` from Lidl SKU.

```python
class ProductCatalog(Protocol):
    def discover(self) -> tuple[ProductReference, ...]: ...
```

```python
class CatalogError(RuntimeError): ...
```

Invalid public argument types raise `TypeError`. Blank reference values raise
`ValueError`. `CatalogError` represents operational retrieval, compression,
XML and catalog-shape failures.

---

## HTTP Boundary

The compressed product sitemap requires a binary HTTP boundary. The existing
`infrastructure.http` package adds `BinaryHttpClient` and the standard-library
`UrllibBinaryHttpClient` reference implementation.

Response size is bounded before content is returned. The catalog also bounds
decompressed XML size. Operational transport and response failures retain the
existing `HttpClientError` boundary and are translated to `CatalogError` by
the catalog implementation.

---

## Discovery Semantics

The Lidl implementation:

1. retrieves the fixed public sitemap index over HTTPS
2. accepts only an HTTPS Czech product-sitemap URL hosted by `lidl.cz`
3. retrieves and decompresses the gzip sitemap within explicit size limits
4. parses URL entries without resolving external entities
5. accepts canonical Czech product URLs whose slug contains `parkside`,
   case-insensitively, and whose terminal identifier matches `p` plus digits
6. emits one reference per external identifier in sitemap order
7. raises `CatalogError` when the catalog contains no Parkside candidates

Slug filtering produces candidates only. The existing product-page provider
remains authoritative for JSON-LD validation and requires the actual brand to
begin with `PARKSIDE`, case-insensitively. This two-stage validation includes
Parkside Performance while rejecting an unrelated candidate before it enters
Domain.

Discovery performs no persistence and fetches no product page. Catalog
comparison, refresh scheduling and observation history belong to later
Application and persistence decisions.

---

## Dependency Direction

```text
future Applications catalog workflow
    +--> core.catalog
    +--> infrastructure.providers.lidl

infrastructure.providers.lidl
    +--> core.catalog
    +--> core.domain
    +--> infrastructure.http
```

Core imports neither HTTP nor the Lidl implementation. Infrastructure does not
import Applications. Home Assistant remains an outer composition root.

---

## Relationship to ADR-0007

ADR-0007 remains authoritative for explicit product-page retrieval. This ADR
supersedes only its deferred discovery limitation by approving a separate
sitemap-based catalog component. Search and pagination crawling remain
rejected.

---

## Alternatives Considered

### Crawl Lidl search or category pages

Rejected because the robots policy disallows the required search and offset
patterns and the page structure is less stable than the published sitemap.

### Add discovery to `LidlParksideProvider.fetch()`

Rejected because explicit monitoring would become an unbounded catalog crawl,
existing callers would change behavior and one provider would acquire
discovery, refresh-policy and persistence responsibilities.

### Fetch every Lidl product page to identify its brand

Rejected because the sitemap currently contains thousands of product URLs.
The URL slug is used as a bounded candidate filter and product JSON-LD remains
the authoritative second-stage brand check.

### Persist discovered references in the catalog implementation

Rejected because Infrastructure discovery must not decide refresh scheduling
or product lifecycle. A later Application workflow will coordinate a durable
catalog repository through explicit contracts.

---

## Consequences

Advantages:

- automatic Parkside candidate discovery from a publisher-advertised source
- no use of disallowed search or pagination endpoints
- unchanged explicit product provider and synchronization workflow
- deterministic, immutable and provider-neutral Core contract
- network-free unit testing through an injected binary client

Costs:

- slug filtering is a candidate heuristic followed by page-level brand checks
- the gzip/XML boundary requires size limits and explicit error handling
- discovery alone does not yet refresh prices, retain history or notify users

---

## References

- https://www.lidl.cz/robots.txt
- https://www.lidl.cz/static/sitemap.xml
