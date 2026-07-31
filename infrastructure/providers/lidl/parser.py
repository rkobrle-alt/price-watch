"""Translate Lidl product-page JSON-LD into Domain products."""

import json
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from uuid import uuid5

from core.domain import (
    Currency,
    Money,
    Percentage,
    Product,
    ProductId,
    ProviderId,
    ValidationError,
)


class LidlProductDataError(ValueError):
    """Report invalid or unsupported Lidl structured product data."""


class _JsonLdExtractor(HTMLParser):
    """Collect JSON-LD script bodies from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.documents: list[str] = []
        self._collecting = False
        self._chunks: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "script":
            return
        attributes = {name.casefold(): value for name, value in attrs}
        script_type = attributes.get("type")
        if script_type is not None and script_type.casefold() == "application/ld+json":
            self._collecting = True
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._collecting:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._collecting:
            self.documents.append("".join(self._chunks))
            self._collecting = False
            self._chunks = []


def parse_lidl_product(
    html: str,
    url: str,
    provider_id: ProviderId,
    captured_at: datetime,
) -> Product:
    """Parse one Parkside product from Lidl product-page HTML."""
    if not isinstance(html, str):
        raise LidlProductDataError("HTTP response body must be text")

    product_data = _find_product_data(html)
    try:
        return _to_product(product_data, url, provider_id, captured_at)
    except ValidationError as error:
        raise LidlProductDataError(str(error)) from error


def _find_product_data(html: str) -> dict[str, object]:
    extractor = _JsonLdExtractor()
    extractor.feed(html)
    malformed = False

    for document in extractor.documents:
        try:
            value = json.loads(document, parse_float=Decimal)
        except json.JSONDecodeError:
            malformed = True
            continue
        for candidate in _iter_schema_objects(value):
            schema_type = candidate.get("@type")
            if schema_type == "Product" or (
                isinstance(schema_type, list) and "Product" in schema_type
            ):
                return candidate

    if malformed:
        raise LidlProductDataError("product JSON-LD is malformed")
    raise LidlProductDataError("product JSON-LD is missing")


def _iter_schema_objects(value: object) -> Iterator[dict[str, object]]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_schema_objects(item)
        return
    if not isinstance(value, dict):
        return
    yield value
    graph = value.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _iter_schema_objects(item)


def _to_product(
    data: dict[str, object],
    url: str,
    provider_id: ProviderId,
    captured_at: datetime,
) -> Product:
    sku = _required_text(data.get("sku"), "sku")
    name = _required_text(data.get("name"), "name")
    brand = _brand_name(data.get("brand"))
    if not brand.casefold().startswith("parkside"):
        raise LidlProductDataError("brand is not Parkside")

    offer = _first_offer(data.get("offers"))
    amount = _price(offer.get("price"))
    currency_code = _required_text(offer.get("priceCurrency"), "price currency")
    try:
        currency = Currency(currency_code)
    except ValueError as error:
        raise LidlProductDataError(f"unsupported currency: {currency_code}") from error

    return Product(
        id=ProductId(uuid5(provider_id.value, sku)),
        provider_id=provider_id,
        brand=brand,
        name=name,
        current_price=Money(amount, currency),
        original_price=None,
        discount_percent=Percentage(Decimal("0")),
        url=url,
        image_url=_image_url(data.get("image")),
        created_at=captured_at,
        availability=_availability(offer.get("availability")),
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LidlProductDataError(f"{field_name} is missing")
    return value.strip()


def _brand_name(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("name")
    return _required_text(value, "brand")


def _first_offer(value: object) -> dict[str, object]:
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, dict):
        raise LidlProductDataError("offer is missing")
    return value


def _price(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise LidlProductDataError("price is invalid")
    try:
        amount = value if isinstance(value, Decimal) else Decimal(value)
    except InvalidOperation as error:
        raise LidlProductDataError("price is invalid") from error
    if not amount.is_finite() or amount < 0:
        raise LidlProductDataError("price is invalid")
    return amount


def _availability(value: object) -> bool:
    text = _required_text(value, "availability")
    name = text.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    if name == "InStock":
        return True
    if name in {"OutOfStock", "SoldOut"}:
        return False
    raise LidlProductDataError(f"unsupported availability: {text}")


def _image_url(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    if not isinstance(value, str):
        raise LidlProductDataError("image is invalid")
    return value.strip() or None
