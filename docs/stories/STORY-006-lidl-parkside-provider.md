# STORY-006: Lidl Parkside Provider

## Goal

Implement the first real Provider SDK adapter for explicitly configured
Parkside tool products on Lidl Czech Republic according to ADR-0007.

---

## Package Structure

Create:

```text
infrastructure/http/
    __init__.py
    client.py
    exceptions.py
    urllib_client.py

infrastructure/providers/
    __init__.py
    lidl/
        __init__.py
        parser.py
        provider.py

tests/unit/providers/
    __init__.py
    fixtures.py
    test_architecture.py
    test_http_client.py
    test_lidl_provider.py
    test_public_api.py
```

---

## Public API

Export through `infrastructure.http`:

- `TextHttpClient`
- `HttpClientError`
- `UrllibTextHttpClient`

Export through `infrastructure.providers.lidl`:

- `LidlParksideProvider`

Every public object must have explicit type hints and a docstring.

---

## TextHttpClient

Define `TextHttpClient` using `typing.Protocol`.

Required method:

```python
get(url: str) -> str
```

The Protocol contains no network implementation.

---

## HttpClientError

`HttpClientError` is the base exception for operational text HTTP retrieval
failures.

It must not be used for invalid public argument types or values.

---

## UrllibTextHttpClient

Constructor:

```python
__init__(
    timeout_seconds: int = 10,
    user_agent: str = "PriceWatch/0.6",
) -> None
```

Requirements:

- `timeout_seconds` must be an `int` other than `bool` and greater than zero
- `user_agent` must be a non-blank `str`
- invalid types raise `TypeError`
- invalid values raise `ValueError`

Public method:

```python
get(url: str) -> str
```

Requirements:

- `url` must be a non-blank `str`
- invalid types raise `TypeError`
- a blank value raises `ValueError`
- send the configured `User-Agent`
- decode the response using its declared charset, defaulting to UTF-8
- wrap `OSError`, `UnicodeError` and HTTP/URL errors in `HttpClientError`
- preserve the original failure as the exception cause

---

## LidlParksideProvider

Constructor:

```python
__init__(
    product_urls: tuple[str, ...],
    http_client: TextHttpClient,
    clock: Callable[[], datetime],
) -> None
```

Configuration requirements:

- `product_urls` must be a non-empty tuple of strings
- URLs must be unique
- every URL must use HTTPS
- every host must be `lidl.cz` or `www.lidl.cz`
- every path must identify an individual product and end with `/p` followed
  by digits
- `http_client` must expose a callable `get`
- `clock` must be callable
- invalid argument types raise `TypeError`
- invalid configuration values raise `ValueError`

The provider exposes:

```python
id: ProviderId
display_name: str
version: str
fetch: Callable[[], FetchResult]
```

Metadata values:

- `display_name` is `"Lidl CZ Parkside"`
- `version` is `"1.0"`
- `id` is stable across instances and process executions

---

## Fetch Behavior

`fetch()` must:

1. read a timezone-aware start timestamp from the injected clock
2. retrieve every configured URL in tuple order
3. parse schema.org JSON-LD from each response
4. convert one valid Parkside `Product` entry per URL
5. continue after an individual supported failure
6. read a timezone-aware finish timestamp from the injected clock
7. return a `FetchResult` with products, errors and elapsed duration

All successfully converted products use the cycle start timestamp as
`Product.created_at`.

Clock values that are not `datetime` instances raise `TypeError`.

Naive clock values and a finish time before the start time raise `ValueError`.

---

## JSON-LD Mapping

The parser must locate a schema.org `Product` object in a top-level object,
array or `@graph`.

Required fields:

- non-blank `sku`
- non-blank `name`
- non-blank brand name
- an `Offer`, directly or as the first item in an offers array
- non-negative price convertible to `Decimal`
- a supported Domain currency
- recognized availability

Accepted availability values, with or without a schema.org URL prefix:

- `InStock` maps to `True`
- `OutOfStock` maps to `False`
- `SoldOut` maps to `False`

The brand must begin with `PARKSIDE`, case-insensitively.

The first image string is used when `image` is an array. A string image is
used directly. Missing image data maps to `None`.

Domain mapping:

- `Product.id` is UUIDv5 derived from provider ID and SKU
- `provider_id` is the provider ID
- `current_price` uses JSON-LD price and currency
- `original_price` is `None`
- `discount_percent` is zero
- `url` is the configured product URL
- `created_at` is the cycle start timestamp

JSON number parsing must never convert money through `float`.

---

## Error Behavior

The following per-product failures add a `ProviderError` to
`FetchResult.errors` and do not abort remaining URLs:

- `HttpClientError`
- malformed JSON-LD
- missing or invalid required product data
- unsupported currency or availability
- non-Parkside brand

Every per-product error message identifies the failed URL and explains the
failure.

Unexpected exceptions are not silently converted.

---

## Dependency Rules

The implementation may import only the dependencies approved by ADR-0007.

No Domain or Provider SDK file may be modified.

No Application, persistence, rule or notification package may be imported by
the provider.

No third-party HTTP or parsing dependency may be added.

---

## Tests

Provide network-free unit tests covering:

- HTTP Protocol compatibility
- HTTP client constructor and URL validation
- request user agent, timeout and response charset handling
- operational and decoding failure wrapping with preserved cause
- Lidl provider compatibility with the Provider Protocol
- valid in-stock and out-of-stock JSON-LD mapping
- top-level array and `@graph` discovery
- string and array image mapping
- exact Decimal prices without float conversion
- stable provider and product IDs
- deterministic ordering and timestamps
- all constructor validation branches
- clock return validation
- each supported per-product failure
- partial success when one URL fails
- unexpected exception propagation
- public package exports
- dependency boundaries

Tests must not access the network, filesystem, database, environment or global
clock.

Target coverage:

- 100% statement coverage
- 100% branch coverage

No skipped tests are allowed.

---

## Acceptance Criteria

- ADR-0007 is followed exactly.
- The existing Domain and Provider SDK are unchanged.
- The provider reads only explicitly configured product URLs.
- No search, catalog or pagination endpoint is used.
- Only Parkside products are returned.
- External data is converted into immutable Domain `Product` objects.
- Product IDs remain stable for equal Lidl SKUs.
- Partial supported failures are returned as `ProviderError` values.
- Core remains Infrastructure-independent and deterministic.
- Public APIs are exported through `__init__.py`.
- Every public object has type hints and a docstring.
- No TODOs, placeholders, pass statements, commented-out code or dead code
  remain.
- All tests pass with 100% statement and branch coverage.

