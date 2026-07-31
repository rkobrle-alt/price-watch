"""Test doubles and JSON-LD fixtures for provider unit tests."""

import json
from collections.abc import Callable
from datetime import datetime

LIDL_URL = "https://www.lidl.cz/p/parkside-performance-kladivo/p100382709"
SECOND_LIDL_URL = "https://lidl.cz/p/parkside-performance-bruska/p100382710"


def product_data(**overrides: object) -> dict[str, object]:
    """Return representative Lidl Parkside JSON-LD data."""
    data: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "sku": "100382709",
        "name": "Aku kombinované kladivo",
        "brand": {"@type": "Brand", "name": "PARKSIDE PERFORMANCE®"},
        "image": ["https://www.lidl.cz/assets/product.jpg"],
        "offers": [
            {
                "@type": "Offer",
                "price": 2399.90,
                "priceCurrency": "CZK",
                "availability": "https://schema.org/InStock",
            }
        ],
    }
    data.update(overrides)
    return data


def product_html(data: object | None = None, prefix: str = "") -> str:
    """Wrap JSON-compatible data in a product-page HTML document."""
    payload = product_data() if data is None else data
    return (
        "<html><head><script>ignored</script>"
        f"{prefix}<script type='application/ld+json'>{json.dumps(payload)}</script>"
        "</head></html>"
    )


class FakeHttpClient:
    """Return configured page content or raise configured failures."""

    def __init__(self, responses: dict[str, str | Exception]) -> None:
        self.responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str) -> str:
        """Return or raise the response configured for *url*."""
        self.requested_urls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def sequence_clock(*values: object) -> Callable[[], object]:
    """Return a clock that emits the supplied values in order."""
    iterator = iter(values)
    return lambda: next(iterator)


def static_clock(value: datetime) -> Callable[[], datetime]:
    """Return a clock that always emits one timestamp."""
    return lambda: value
