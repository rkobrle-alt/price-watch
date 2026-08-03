"""Strict parsing helpers for Lidl sitemap catalog discovery."""

import re
from typing import cast
from urllib.parse import ParseResult, urlparse, urlunparse
from xml.etree import ElementTree

from core.catalog import ProductReference
from core.domain import ProviderId

_SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
_INDEX_TAG = f"{{{_SITEMAP_NAMESPACE}}}sitemapindex"
_URLSET_TAG = f"{{{_SITEMAP_NAMESPACE}}}urlset"
_SITEMAP_LOCATION = f"{{{_SITEMAP_NAMESPACE}}}sitemap/{{{_SITEMAP_NAMESPACE}}}loc"
_PRODUCT_LOCATION = f"{{{_SITEMAP_NAMESPACE}}}url/{{{_SITEMAP_NAMESPACE}}}loc"
_PRODUCT_SITEMAP_PATH = "/p/export/CZ/cs/product_sitemap.xml.gz"
_PRODUCT_PATH = re.compile(
    r"^/p/(?P<slug>(?i:[^/]*parkside[^/]*))/(?P<external_id>p[0-9]+)$",
)
_LIDL_HOSTS = {"lidl.cz", "www.lidl.cz"}


def parse_product_sitemap_location(xml: bytes) -> str:
    """Return the one approved Czech Lidl product-sitemap location."""
    root = ElementTree.fromstring(xml)
    if root.tag != _INDEX_TAG:
        raise ValueError("sitemap index root is invalid")
    locations = [
        element.text.strip()
        for element in root.findall(_SITEMAP_LOCATION)
        if element.text is not None
        and _is_canonical_lidl_url(element.text.strip(), _PRODUCT_SITEMAP_PATH)
    ]
    if len(locations) != 1:
        raise ValueError("sitemap index must contain exactly one product sitemap")
    return locations[0]


def parse_product_references(
    xml: bytes,
    provider_id: ProviderId,
) -> tuple[ProductReference, ...]:
    """Return ordered, identifier-deduplicated Parkside product references."""
    root = ElementTree.fromstring(xml)
    if root.tag != _URLSET_TAG:
        raise ValueError("product sitemap root is invalid")

    references: list[ProductReference] = []
    seen: set[str] = set()
    for element in root.findall(_PRODUCT_LOCATION):
        if element.text is None:
            continue
        parsed = _parse_product_url(element.text.strip())
        if parsed is None:
            continue
        external_id, url = parsed
        if external_id in seen:
            continue
        seen.add(external_id)
        references.append(ProductReference(provider_id, external_id, url))
    return tuple(references)


def validate_sitemap_index_url(url: object) -> str:
    """Validate and return the fixed Lidl sitemap-index URL."""
    if not isinstance(url, str):
        raise TypeError("sitemap_index_url must be a str")
    if not _is_canonical_lidl_url(url, "/static/sitemap.xml"):
        raise ValueError("sitemap_index_url must be the canonical Lidl sitemap URL")
    return url


def _parse_product_url(url: str) -> tuple[str, str] | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if not _has_canonical_lidl_authority(parsed):
        return None
    if parsed.query or parsed.fragment:
        return None
    match = _PRODUCT_PATH.fullmatch(parsed.path)
    if match is None:
        return None
    host = cast(str, parsed.hostname)
    canonical_url = urlunparse(("https", host.lower(), parsed.path, "", "", ""))
    return match.group("external_id"), canonical_url


def _is_canonical_lidl_url(url: str, expected_path: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (
        _has_canonical_lidl_authority(parsed)
        and parsed.path == expected_path
        and not parsed.query
        and not parsed.fragment
    )


def _has_canonical_lidl_authority(parsed: ParseResult) -> bool:
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and hostname is not None
        and hostname.lower() in _LIDL_HOSTS
        and parsed.username is None
        and parsed.password is None
        and port is None
    )
