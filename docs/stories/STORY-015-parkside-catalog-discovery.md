# STORY-015: Parkside Catalog Discovery

## Objective

Implement the provider-neutral catalog contract and the first Lidl Czech
Republic Parkside discovery implementation according to ADR-0016.

This story discovers immutable product references only. It does not retrieve
product pages, persist catalog membership, change synchronization, evaluate
rules or send notifications.

## Scope

Create:

```text
core/catalog/
    __init__.py
    contract.py
    exceptions.py
    reference.py

infrastructure/http/
    binary_client.py
    urllib_binary_client.py

infrastructure/providers/lidl/
    catalog.py
    sitemap_parser.py
```

Modify public package exports and add unit tests under the corresponding
`tests/unit` packages.

Do not modify the Domain entities, existing `Provider` contract,
`LidlParksideProvider`, synchronization workflow, State Store, Rule Engine,
notification packages, CLI or Home Assistant application behavior.

## Public API

### `core.catalog`

Export the immutable `ProductReference`, structural `ProductCatalog` Protocol
and `CatalogError` exception documented by ADR-0016.

`ProductReference` validation:

- `provider_id` must be `ProviderId`
- `external_id` and `url` must be strings
- blank or whitespace-only strings raise `ValueError`
- invalid argument types raise `TypeError`

### `infrastructure.http`

Export:

```python
class BinaryHttpClient(Protocol):
    def get(self, url: str) -> bytes: ...
```

Export:

```python
UrllibBinaryHttpClient(
    timeout_seconds: int = 10,
    user_agent: str = "PriceWatch/0.15",
    max_response_bytes: int = 20 * 1024 * 1024,
    opener: Callable[..., ContextManager[BinaryIO]] = urlopen,
)
```

`get(url: str) -> bytes` must accept only non-blank HTTP or HTTPS URLs, send
the configured user agent, read at most `max_response_bytes + 1` bytes, close
every response and return bytes without decoding. Oversized responses and
operational HTTP, URL, timeout or read failures raise `HttpClientError` with
exception chaining.

Constructor integer values reject `bool` and must be positive. Invalid public
types raise `TypeError`; invalid values raise `ValueError`; the opener must be
callable. Existing text HTTP APIs remain unchanged.

### `infrastructure.providers.lidl`

Export:

```python
LidlParksideCatalog(
    http_client: BinaryHttpClient,
    sitemap_index_url: str = "https://www.lidl.cz/static/sitemap.xml",
    max_decompressed_bytes: int = 20 * 1024 * 1024,
)
```

It exposes `discover() -> tuple[ProductReference, ...]` and uses the same
stable Lidl `ProviderId` as `LidlParksideProvider`.

Constructor validation is explicit:

- `http_client` must structurally expose a callable `get`
- `sitemap_index_url` must be a string containing exactly an HTTPS `lidl.cz`
  or `www.lidl.cz` `/static/sitemap.xml` URL without credentials, port, query
  or fragment
- `max_decompressed_bytes` must be a positive `int` and reject `bool`

## Discovery Behavior

One `discover()` call must:

1. retrieve `sitemap_index_url`
2. parse a sitemap index using the sitemap XML namespace
3. select exactly one HTTPS `lidl.cz` product sitemap whose path is
   `/p/export/CZ/cs/product_sitemap.xml.gz`
4. retrieve it through the injected binary client
5. require gzip input and bound decompressed content
6. parse a URL set without external entity or network resolution
7. accept only canonical HTTPS `lidl.cz` product URLs with a `/p/` path, a
   slug containing `parkside` case-insensitively and a terminal `p` plus
   decimal digits identifier
8. emit references in source order and deduplicate by external identifier,
   preserving the first accepted occurrence

Credentials, explicit ports, query strings and fragments are rejected. Emitted
URLs normalize the host to lowercase and otherwise preserve the accepted path.

No search, offset, sorting, advisor, listing or product-page endpoint may be
requested. An empty accepted Parkside result raises `CatalogError`.

## Failure Semantics

The catalog translates `HttpClientError`, malformed or invalid sitemap XML,
missing or duplicate product sitemap locations, non-gzip data, gzip
corruption, decompressed-size overflow and an empty result to `CatalogError`.
An underlying exception is chained when one exists; an empty semantic result
raises `CatalogError` directly. Invalid constructor types raise `TypeError`,
invalid values raise `ValueError`, and unexpected programming errors propagate.

No partial result is returned after a catalog failure.

## Architecture Boundaries

`core.catalog` may depend only on public Domain identifiers and the standard
library. The Lidl implementation may depend on `core.catalog`, public Domain
identifiers, `infrastructure.http` and standard-library URL, XML and gzip
modules.

It must not import Applications, persistence, rules, notifications, Home
Assistant or databases. It performs no filesystem access, persistence,
logging, clock reads or identifier generation.

## Unit Tests

Tests must cover:

- reference immutability, equality and every validation branch
- structural Protocol compatibility and exception hierarchy
- binary request headers, exact bytes, limits, closure and error chaining
- sitemap-index selection and validation
- gzip parsing and decompressed-size limits
- Parkside and Parkside Performance matching across all approved product types
- rejection of wrong hosts, schemes, paths, identifiers, queries and fragments
- ordering, deduplication, empty results and every documented failure path
- exact requested URL sequence proving no search, pagination or product pages
- public exports and dependency boundaries

Tests must not access the network or filesystem.

## Acceptance Criteria

- public APIs match this story exactly and are exported through `__init__.py`
- existing explicit Lidl provider behavior remains backward compatible
- discovery reads only the approved sitemap index and product sitemap
- returned references are immutable and deterministic
- no product page, persistence, rule or notification behavior is added
- every public object has type hints and a docstring
- no TODOs, placeholders, `pass`, skipped tests, commented-out code or dead code
- the complete suite passes with 100 percent statement and branch coverage
