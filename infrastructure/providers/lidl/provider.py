"""Provider SDK adapter for Lidl Czech Republic Parkside products."""

import re
from collections.abc import Callable
from datetime import datetime
from typing import cast
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

from core.domain import Product, ProviderId
from core.provider import (
    FetchResult,
    ProviderDataError,
    ProviderError,
    ProviderTransportError,
)
from infrastructure.http import HttpClientError, TextHttpClient
from infrastructure.providers.lidl.parser import (
    LidlProductDataError,
    parse_lidl_product,
)

_PRODUCT_PATH = re.compile(r"/.+/p\d+")


class LidlParksideProvider:
    """Retrieve configured Parkside tool products from Lidl Czech Republic."""

    id: ProviderId = ProviderId(
        uuid5(NAMESPACE_URL, "https://www.lidl.cz/parkside")
    )
    display_name: str = "Lidl CZ Parkside"
    version: str = "1.0"

    def __init__(
        self,
        product_urls: tuple[str, ...],
        http_client: TextHttpClient,
        clock: Callable[[], datetime],
    ) -> None:
        """Configure explicit product URLs and injected side-effect providers."""
        self._product_urls = _validate_product_urls(product_urls)
        if not callable(getattr(http_client, "get", None)):
            raise TypeError("http_client must expose a callable get method")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._http_client = cast(TextHttpClient, http_client)
        self._clock = clock

    def fetch(self) -> FetchResult:
        """Retrieve configured products and report supported partial failures."""
        started_at = self._read_clock()
        products: list[Product] = []
        errors: list[ProviderError] = []

        for url in self._product_urls:
            try:
                html = self._http_client.get(url)
                products.append(parse_lidl_product(html, url, self.id, started_at))
            except HttpClientError as error:
                errors.append(ProviderTransportError(f"{url}: {error}"))
            except LidlProductDataError as error:
                errors.append(ProviderDataError(f"{url}: {error}"))

        finished_at = self._read_clock()
        if finished_at < started_at:
            raise ValueError("clock finish time cannot be before start time")
        return FetchResult(
            products=tuple(products),
            started_at=started_at,
            finished_at=finished_at,
            duration=finished_at - started_at,
            errors=tuple(errors),
        )

    def _read_clock(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock must return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value


def _validate_product_urls(product_urls: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(product_urls, tuple) or not all(
        isinstance(url, str) for url in product_urls
    ):
        raise TypeError("product_urls must be a tuple of strings")
    if not product_urls:
        raise ValueError("product_urls cannot be empty")
    if len(set(product_urls)) != len(product_urls):
        raise ValueError("product_urls must be unique")

    for url in product_urls:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("product URLs must use HTTPS")
        if parsed.hostname not in {"lidl.cz", "www.lidl.cz"}:
            raise ValueError("product URLs must use the Lidl Czech Republic host")
        if _PRODUCT_PATH.fullmatch(parsed.path) is None:
            raise ValueError("product URLs must identify an individual product")
    return product_urls
