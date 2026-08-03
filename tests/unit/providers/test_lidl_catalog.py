"""Tests for Lidl Czech Republic Parkside sitemap discovery."""

from gzip import compress
from html import escape
from typing import cast

import pytest

from core.catalog import CatalogError, ProductCatalog, ProductReference
from infrastructure.http import HttpClientError
from infrastructure.providers.lidl import LidlParksideCatalog, LidlParksideProvider

_INDEX_URL = "https://www.lidl.cz/static/sitemap.xml"
_PRODUCT_SITEMAP_URL = (
    "https://www.lidl.cz/p/export/CZ/cs/product_sitemap.xml.gz"
)
_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"


class _BinaryClient:
    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str) -> bytes:
        self.requested_urls.append(url)
        response = self._responses[url]
        if isinstance(response, Exception):
            raise response
        return cast(bytes, response)


def _index(*locations: str | None, root: str = "sitemapindex") -> bytes:
    entries = "".join(
        "<sitemap><loc></loc></sitemap>"
        if location is None
        else f"<sitemap><loc>{escape(location)}</loc></sitemap>"
        for location in locations
    )
    return f'<{root} xmlns="{_NAMESPACE}">{entries}</{root}>'.encode()


def _urlset(*locations: str | None, root: str = "urlset") -> bytes:
    entries = "".join(
        "<url><loc></loc></url>"
        if location is None
        else f"<url><loc>{escape(location)}</loc></url>"
        for location in locations
    )
    return f'<{root} xmlns="{_NAMESPACE}">{entries}</{root}>'.encode()


def _client_for_product_xml(product_xml: bytes) -> _BinaryClient:
    return _BinaryClient(
        {
            _INDEX_URL: _index(_PRODUCT_SITEMAP_URL),
            _PRODUCT_SITEMAP_URL: compress(product_xml),
        }
    )


def _as_catalog(catalog: ProductCatalog) -> ProductCatalog:
    return catalog


def test_catalog_implements_protocol_and_reuses_provider_identity() -> None:
    catalog = LidlParksideCatalog(_client_for_product_xml(_urlset(
        "https://lidl.cz/p/parkside-tool/p1"
    )))

    assert _as_catalog(catalog) is catalog
    assert catalog.id == LidlParksideProvider.id


@pytest.mark.parametrize("client", [None, object()])
def test_constructor_rejects_client_without_callable_get(client: object) -> None:
    with pytest.raises(TypeError, match="http_client"):
        LidlParksideCatalog(client)  # type: ignore[arg-type]


def test_constructor_accepts_structural_binary_client() -> None:
    client = _client_for_product_xml(_urlset("https://lidl.cz/p/parkside-tool/p1"))

    assert LidlParksideCatalog(client).discover()[0].external_id == "p1"


@pytest.mark.parametrize("url", [None, 42])
def test_constructor_rejects_invalid_index_url_type(url: object) -> None:
    with pytest.raises(TypeError, match="sitemap_index_url"):
        LidlParksideCatalog(_BinaryClient({}), sitemap_index_url=url)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://www.lidl.cz/static/sitemap.xml",
        "https://example.cz/static/sitemap.xml",
        "https://www.lidl.cz/STATIC/sitemap.xml",
        "https://user@www.lidl.cz/static/sitemap.xml",
        "https://www.lidl.cz:443/static/sitemap.xml",
        "https://www.lidl.cz/static/sitemap.xml?x=1",
        "https://www.lidl.cz/static/sitemap.xml#fragment",
        "https://www.lidl.cz/static/sitemap.xml/",
        "https://www.lidl.cz:invalid/static/sitemap.xml",
        "https://[invalid/static/sitemap.xml",
    ],
)
def test_constructor_rejects_noncanonical_index_url(url: str) -> None:
    with pytest.raises(ValueError, match="sitemap_index_url"):
        LidlParksideCatalog(_BinaryClient({}), sitemap_index_url=url)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url",
    [
        "https://lidl.cz/static/sitemap.xml",
        "https://www.lidl.cz/static/sitemap.xml",
        "https://WWW.LIDL.CZ/static/sitemap.xml",
    ],
)
def test_constructor_accepts_approved_index_hosts(url: str) -> None:
    client = _BinaryClient(
        {
            url: _index(_PRODUCT_SITEMAP_URL),
            _PRODUCT_SITEMAP_URL: compress(
                _urlset("https://lidl.cz/p/parkside-tool/p1")
            ),
        }
    )

    assert LidlParksideCatalog(client, sitemap_index_url=url).discover()


@pytest.mark.parametrize("limit", [True, 1.5, "20"])
def test_constructor_rejects_invalid_decompressed_limit_type(limit: object) -> None:
    with pytest.raises(TypeError, match="max_decompressed_bytes"):
        LidlParksideCatalog(
            _BinaryClient({}),
            max_decompressed_bytes=limit,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("limit", [0, -1])
def test_constructor_rejects_non_positive_decompressed_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="max_decompressed_bytes"):
        LidlParksideCatalog(_BinaryClient({}), max_decompressed_bytes=limit)


def test_discover_returns_all_approved_product_types_in_source_order() -> None:
    urls = (
        "https://WWW.LIDL.CZ/p/PARKSIDE-performance-drill/p101",
        "https://lidl.cz/p/parkside-zahradni-sekacka/p102",
        "https://www.lidl.cz/p/parkside-akumulator/p103",
        "https://www.lidl.cz/p/parkside-nabijecka/p104",
        "https://www.lidl.cz/p/parkside-prislusenstvi/p105",
    )
    client = _client_for_product_xml(_urlset(*urls))

    references = LidlParksideCatalog(client).discover()

    assert references == tuple(
        ProductReference(
            LidlParksideProvider.id,
            f"p{identifier}",
            url.replace("WWW.LIDL.CZ", "www.lidl.cz"),
        )
        for identifier, url in zip(range(101, 106), urls, strict=True)
    )
    assert client.requested_urls == [_INDEX_URL, _PRODUCT_SITEMAP_URL]


def test_discover_selects_only_the_approved_product_sitemap() -> None:
    other = "https://www.lidl.cz/c/export/CZ/cs/category_sitemap.xml.gz"
    client = _BinaryClient(
        {
            _INDEX_URL: _index(other, _PRODUCT_SITEMAP_URL),
            _PRODUCT_SITEMAP_URL: compress(
                _urlset("https://lidl.cz/p/parkside-tool/p1")
            ),
        }
    )

    assert LidlParksideCatalog(client).discover()
    assert client.requested_urls == [_INDEX_URL, _PRODUCT_SITEMAP_URL]


def test_discover_deduplicates_by_identifier_and_preserves_first() -> None:
    first = "https://lidl.cz/p/parkside-first/p123"
    client = _client_for_product_xml(
        _urlset(
            first,
            "https://www.lidl.cz/p/parkside-duplicate/p123",
            "https://lidl.cz/p/parkside-next/p456",
        )
    )

    references = LidlParksideCatalog(client).discover()

    assert [reference.external_id for reference in references] == ["p123", "p456"]
    assert references[0].url == first


def test_discover_rejects_noncanonical_product_candidates() -> None:
    valid = "https://lidl.cz/p/parkside-valid/p999"
    invalid = (
        None,
        "http://lidl.cz/p/parkside-tool/p1",
        "https://example.cz/p/parkside-tool/p2",
        "https://lidl.cz/c/parkside-tool/p3",
        "https://lidl.cz/p/other-brand/p4",
        "https://lidl.cz/p/parkside-tool/not-an-id",
        "https://lidl.cz/p/parkside-tool/P5",
        "https://lidl.cz/p/parkside-tool/p6/",
        "https://lidl.cz/p/parkside-tool/p7?tracking=1",
        "https://lidl.cz/p/parkside-tool/p8#fragment",
        "https://user@lidl.cz/p/parkside-tool/p9",
        "https://lidl.cz:443/p/parkside-tool/p10",
        "https://lidl.cz/p/category/parkside-tool/p11",
        "https://lidl.cz:invalid/p/parkside-tool/p12",
        "https://[invalid/p/parkside-tool/p13",
    )
    client = _client_for_product_xml(_urlset(*invalid, valid))

    assert LidlParksideCatalog(client).discover() == (
        ProductReference(LidlParksideProvider.id, "p999", valid),
    )


@pytest.mark.parametrize(
    "index_xml",
    [
        b"<not-xml",
        (
            b'<!DOCTYPE urlset [<!ENTITY remote SYSTEM "https://example.invalid/">]>'
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<url><loc>&remote;</loc></url></urlset>"
        ),
        b"<urlset></urlset>",
        _index(_PRODUCT_SITEMAP_URL, root="urlset"),
        _index(),
        _index(None),
        _index("https://example.cz/p/export/CZ/cs/product_sitemap.xml.gz"),
        _index("http://www.lidl.cz/p/export/CZ/cs/product_sitemap.xml.gz"),
        _index("https://user@www.lidl.cz/p/export/CZ/cs/product_sitemap.xml.gz"),
        _index("https://www.lidl.cz:443/p/export/CZ/cs/product_sitemap.xml.gz"),
        _index(_PRODUCT_SITEMAP_URL + "#fragment"),
        _index("https://www.lidl.cz/p/export/CZ/cs/wrong.xml.gz"),
        b"<sitemapindex></sitemapindex>",
        _index(_PRODUCT_SITEMAP_URL + "?query=1"),
        _index(_PRODUCT_SITEMAP_URL, _PRODUCT_SITEMAP_URL),
    ],
)
def test_discover_rejects_invalid_sitemap_index(index_xml: bytes) -> None:
    client = _BinaryClient({_INDEX_URL: index_xml})

    with pytest.raises(CatalogError, match="invalid Lidl catalog") as captured:
        LidlParksideCatalog(client).discover()

    assert captured.value.__cause__ is not None
    assert client.requested_urls == [_INDEX_URL]


def test_discover_translates_http_failure_with_cause() -> None:
    failure = HttpClientError("offline")
    client = _BinaryClient({_INDEX_URL: failure})

    with pytest.raises(CatalogError, match="retrieve Lidl catalog") as captured:
        LidlParksideCatalog(client).discover()

    assert captured.value.__cause__ is failure


def test_discover_translates_product_sitemap_http_failure() -> None:
    failure = HttpClientError("product sitemap offline")
    client = _BinaryClient(
        {
            _INDEX_URL: _index(_PRODUCT_SITEMAP_URL),
            _PRODUCT_SITEMAP_URL: failure,
        }
    )

    with pytest.raises(CatalogError, match="retrieve Lidl catalog") as captured:
        LidlParksideCatalog(client).discover()

    assert captured.value.__cause__ is failure
    assert client.requested_urls == [_INDEX_URL, _PRODUCT_SITEMAP_URL]


def test_discover_rejects_non_gzip_product_sitemap() -> None:
    client = _BinaryClient(
        {
            _INDEX_URL: _index(_PRODUCT_SITEMAP_URL),
            _PRODUCT_SITEMAP_URL: b"plain XML",
        }
    )

    with pytest.raises(CatalogError) as captured:
        LidlParksideCatalog(client).discover()

    assert isinstance(captured.value.__cause__, ValueError)


def test_discover_rejects_corrupt_gzip_product_sitemap() -> None:
    client = _BinaryClient(
        {
            _INDEX_URL: _index(_PRODUCT_SITEMAP_URL),
            _PRODUCT_SITEMAP_URL: bytes([31, 139]) + b"corrupt",
        }
    )

    with pytest.raises(CatalogError) as captured:
        LidlParksideCatalog(client).discover()

    assert isinstance(captured.value.__cause__, (OSError, EOFError))


def test_discover_rejects_decompressed_size_overflow() -> None:
    product_xml = _urlset("https://lidl.cz/p/parkside-tool/p1")
    client = _client_for_product_xml(product_xml)

    with pytest.raises(CatalogError) as captured:
        LidlParksideCatalog(
            client,
            max_decompressed_bytes=len(product_xml) - 1,
        ).discover()

    assert isinstance(captured.value.__cause__, ValueError)


@pytest.mark.parametrize(
    "product_xml",
    [
        b"<not-xml",
        (
            b'<!DOCTYPE urlset [<!ENTITY remote SYSTEM "https://example.invalid/">]>'
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<url><loc>&remote;</loc></url></urlset>"
        ),
        b"<urlset></urlset>",
        _urlset("https://lidl.cz/p/parkside-tool/p1", root="sitemapindex"),
    ],
)
def test_discover_rejects_invalid_product_sitemap_xml(product_xml: bytes) -> None:
    with pytest.raises(CatalogError, match="invalid Lidl catalog") as captured:
        LidlParksideCatalog(_client_for_product_xml(product_xml)).discover()

    assert captured.value.__cause__ is not None


def test_discover_rejects_empty_result_without_chained_cause() -> None:
    client = _client_for_product_xml(_urlset(None, "https://lidl.cz/p/other/p1"))

    with pytest.raises(CatalogError, match="no Parkside") as captured:
        LidlParksideCatalog(client).discover()

    assert captured.value.__cause__ is None


def test_discover_propagates_unexpected_programming_error() -> None:
    client = _BinaryClient(
        {
            _INDEX_URL: _index(_PRODUCT_SITEMAP_URL),
            _PRODUCT_SITEMAP_URL: "not bytes",
        }
    )

    with pytest.raises(TypeError, match="must be bytes"):
        LidlParksideCatalog(client).discover()
