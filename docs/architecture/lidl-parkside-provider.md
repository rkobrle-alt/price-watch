# Lidl Parkside Provider Architecture

## Purpose

The Lidl Parkside provider retrieves explicitly configured Parkside tool
product pages from Lidl Czech Republic and translates their JSON-LD into
Domain `Product` objects.

It is the first concrete implementation of the Provider SDK.

---

## Packages

```text
infrastructure/
    http/
        __init__.py
        client.py
        exceptions.py
        urllib_client.py
    providers/
        __init__.py
        lidl/
            __init__.py
            parser.py
            provider.py
```

`infrastructure.http` isolates text retrieval from provider translation.

`infrastructure.providers.lidl` owns Lidl-specific validation and mapping.

---

## Public API

The `infrastructure.http` package exports:

- `TextHttpClient`
- `HttpClientError`
- `UrllibTextHttpClient`

The `infrastructure.providers.lidl` package exports:

- `LidlParksideProvider`

### TextHttpClient

```python
get(url: str) -> str
```

### UrllibTextHttpClient

```python
UrllibTextHttpClient(
    timeout_seconds: int = 10,
    user_agent: str = "PriceWatch/0.6",
)
```

### LidlParksideProvider

```python
LidlParksideProvider(
    product_urls: tuple[str, ...],
    http_client: TextHttpClient,
    clock: Callable[[], datetime],
)
```

The provider exposes the existing Provider attributes:

- `id`
- `display_name`
- `version`
- `fetch`

---

## Fetch Flow

```text
Configured product URL
        |
        v
TextHttpClient.get
        |
        v
JSON-LD parser
        |
        v
Domain Product
        |
        v
FetchResult
```

Each configured URL is processed independently. A supported failure adds one
`ProviderError` and processing continues.

The returned product order and error order follow configured URL order.

---

## Boundaries

The provider may depend on:

- `core.domain`
- the public `core.provider` API
- `infrastructure.http`
- Python standard library modules

It must not depend on:

- Applications
- State Store implementations
- Rule Engine
- Notification Engine
- Home Assistant
- databases

Core does not import the Lidl provider or HTTP package.

---

## Configuration

Product discovery is outside this provider.

Applications supply a non-empty tuple of unique HTTPS Lidl Czech Republic
product URLs, an HTTP implementation and a clock.

The provider has no environment-variable, filesystem or global-clock
dependency.

---

## Determinism

Provider and product identifiers are stable.

With equal page content, configured URLs and clock values, the provider
returns equal Domain values and timing information.

The only side effects are the injected clock reads and HTTP client calls.

