"""Lidl Czech Republic Parkside sitemap catalog adapter."""

from gzip import GzipFile
from io import BytesIO
from typing import cast
from xml.etree import ElementTree

from core.catalog import CatalogError, ProductReference
from core.domain import ProviderId
from infrastructure.http import BinaryHttpClient, HttpClientError
from infrastructure.providers.lidl.provider import LidlParksideProvider
from infrastructure.providers.lidl.sitemap_parser import (
    parse_product_references,
    parse_product_sitemap_location,
    validate_sitemap_index_url,
)

_DEFAULT_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024


class LidlParksideCatalog:
    """Discover Parkside candidates from the published Lidl Czech sitemap."""

    id: ProviderId = LidlParksideProvider.id

    def __init__(
        self,
        http_client: BinaryHttpClient,
        sitemap_index_url: str = "https://www.lidl.cz/static/sitemap.xml",
        max_decompressed_bytes: int = _DEFAULT_MAX_DECOMPRESSED_BYTES,
    ) -> None:
        """Configure the binary client, fixed index and decompression limit."""
        if not callable(getattr(http_client, "get", None)):
            raise TypeError("http_client must expose a callable get method")
        self._http_client = cast(BinaryHttpClient, http_client)
        self._sitemap_index_url = validate_sitemap_index_url(sitemap_index_url)
        self._max_decompressed_bytes = _positive_int(
            max_decompressed_bytes, "max_decompressed_bytes"
        )

    def discover(self) -> tuple[ProductReference, ...]:
        """Discover ordered Parkside product references without fetching pages."""
        try:
            index_xml = self._http_client.get(self._sitemap_index_url)
            product_sitemap_url = parse_product_sitemap_location(index_xml)
            compressed_xml = self._http_client.get(product_sitemap_url)
            product_xml = _decompress_gzip(
                compressed_xml,
                self._max_decompressed_bytes,
            )
            references = parse_product_references(product_xml, self.id)
        except HttpClientError as error:
            raise CatalogError("failed to retrieve Lidl catalog") from error
        except (ElementTree.ParseError, OSError, EOFError, ValueError) as error:
            raise CatalogError("invalid Lidl catalog") from error
        if not references:
            raise CatalogError("Lidl catalog contains no Parkside products")
        return references


def _decompress_gzip(payload: bytes, max_bytes: int) -> bytes:
    if not isinstance(payload, bytes):
        raise TypeError("product sitemap response must be bytes")
    if not payload.startswith(bytes([31, 139])):
        raise ValueError("product sitemap must be gzip data")
    with GzipFile(fileobj=BytesIO(payload), mode="rb") as stream:
        decompressed = stream.read(max_bytes + 1)
    if len(decompressed) > max_bytes:
        raise ValueError("decompressed product sitemap exceeds size limit")
    return decompressed


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value
