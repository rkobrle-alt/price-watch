"""Tests for Lidl Parkside product translation and fetching."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid5

import pytest

from core.domain import Currency, ProductId
from core.provider import Provider, ProviderError
from infrastructure.http import HttpClientError
from infrastructure.providers.lidl import LidlParksideProvider
from infrastructure.providers.lidl.parser import (
    LidlProductDataError,
    parse_lidl_product,
)
from tests.unit.providers.fixtures import (
    LIDL_URL,
    SECOND_LIDL_URL,
    FakeHttpClient,
    product_data,
    product_html,
    sequence_clock,
    static_clock,
)

START = datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc)
FINISH = START + timedelta(seconds=2)


def _as_provider(provider: Provider) -> Provider:
    return provider


def _provider(
    client: object,
    clock: object | None = None,
    urls: tuple[str, ...] = (LIDL_URL,),
) -> LidlParksideProvider:
    selected_clock = sequence_clock(START, FINISH) if clock is None else clock
    return LidlParksideProvider(
        urls,
        client,  # type: ignore[arg-type]
        selected_clock,  # type: ignore[arg-type]
    )


def test_provider_implements_contract_and_has_stable_metadata() -> None:
    client = FakeHttpClient({LIDL_URL: product_html()})
    first = _provider(client)
    second = _provider(client)

    assert _as_provider(first) is first
    assert first.id == second.id
    assert first.display_name == "Lidl CZ Parkside"
    assert first.version == "1.0"
    assert callable(first.fetch)


def test_fetch_maps_lidl_json_ld_to_domain_product() -> None:
    client = FakeHttpClient({LIDL_URL: product_html()})

    result = _provider(client).fetch()

    assert result.started_at == START
    assert result.finished_at == FINISH
    assert result.duration == timedelta(seconds=2)
    assert result.errors == ()
    assert client.requested_urls == [LIDL_URL]
    assert len(result.products) == 1
    product = result.products[0]
    assert product.id == ProductId(uuid5(LidlParksideProvider.id.value, "100382709"))
    assert product.provider_id == LidlParksideProvider.id
    assert product.brand == "PARKSIDE PERFORMANCE\N{REGISTERED SIGN}"
    assert product.name == "Aku kombinovan\u00e9 kladivo"
    assert product.current_price.amount == Decimal("2399.9")
    assert product.currency is Currency.CZK
    assert product.original_price is None
    assert product.discount_percent.value == Decimal("0")
    assert product.url == LIDL_URL
    assert product.image_url == "https://www.lidl.cz/assets/product.jpg"
    assert product.created_at == START
    assert product.availability is True


@pytest.mark.parametrize(
    ("wrapped", "availability", "image", "expected_available", "expected_image"),
    [
        ("array", "SoldOut", "https://image.test/tool.jpg", False, "https://image.test/tool.jpg"),
        ("graph", "http://schema.org/OutOfStock", [], False, None),
        ("direct", "InStock", "  ", True, None),
    ],
)
def test_parser_supports_document_shapes_and_optional_images(
    wrapped: str,
    availability: str,
    image: object,
    expected_available: bool,
    expected_image: str | None,
) -> None:
    data = product_data(
        **{
            "@type": ["Thing", "Product"] if wrapped == "direct" else "Product",
            "brand": "PARKSIDE",
            "offers": {
                "price": 1699,
                "priceCurrency": "EUR",
                "availability": availability,
            },
            "image": image,
        }
    )
    if wrapped == "array":
        document: object = [{"@type": "Organization"}, data]
    elif wrapped == "graph":
        document = {"@context": "https://schema.org", "@graph": [data]}
    else:
        document = data

    product = parse_lidl_product(
        product_html(document),
        LIDL_URL,
        LidlParksideProvider.id,
        START,
    )

    assert product.current_price.amount == Decimal("1699")
    assert product.currency is Currency.EUR
    assert product.availability is expected_available
    assert product.image_url == expected_image


def test_parser_maps_missing_image_to_none() -> None:
    data = product_data()
    data.pop("image")

    product = parse_lidl_product(
        product_html(data), LIDL_URL, LidlParksideProvider.id, START
    )

    assert product.image_url is None


def test_parser_ignores_malformed_non_product_script_when_product_exists() -> None:
    prefix = "<script type='application/ld+json'>{broken</script>"

    product = parse_lidl_product(
        product_html(prefix=prefix),
        LIDL_URL,
        LidlParksideProvider.id,
        START,
    )
    assert product.name == "Aku kombinovan\u00e9 kladivo"


@pytest.mark.parametrize(
    ("html", "message"),
    [
        ("<script type='application/ld+json'>{broken</script>", "malformed"),
        (product_html({"@type": "Organization"}), "missing"),
        (product_html(42), "missing"),
        (product_html([]), "missing"),
        (product_html({"@graph": []}), "missing"),
    ],
)
def test_parser_rejects_missing_or_malformed_product_json_ld(
    html: str,
    message: str,
) -> None:
    with pytest.raises(LidlProductDataError, match=message):
        parse_lidl_product(html, LIDL_URL, LidlParksideProvider.id, START)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"sku": " "}, "sku"),
        ({"name": None}, "name"),
        ({"brand": {}}, "brand"),
        ({"brand": "Other"}, "not Parkside"),
        ({"offers": []}, "offer"),
        ({"offers": "none"}, "offer"),
        ({"offers": {"price": True, "priceCurrency": "CZK", "availability": "InStock"}}, "price"),
        ({"offers": {"price": "invalid", "priceCurrency": "CZK", "availability": "InStock"}}, "price"),
        ({"offers": {"price": "NaN", "priceCurrency": "CZK", "availability": "InStock"}}, "price"),
        ({"offers": {"price": -1, "priceCurrency": "CZK", "availability": "InStock"}}, "price"),
        ({"offers": {"price": 1, "priceCurrency": "GBP", "availability": "InStock"}}, "currency"),
        ({"offers": {"price": 1, "priceCurrency": "CZK", "availability": None}}, "availability"),
        ({"offers": {"price": 1, "priceCurrency": "CZK", "availability": "PreOrder"}}, "availability"),
        ({"image": 5}, "image"),
    ],
)
def test_parser_rejects_invalid_external_product_data(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(LidlProductDataError, match=message):
        parse_lidl_product(
            product_html(product_data(**overrides)),
            LIDL_URL,
            LidlParksideProvider.id,
            START,
        )


def test_parser_rejects_non_text_body() -> None:
    with pytest.raises(LidlProductDataError, match="body"):
        parse_lidl_product(42, LIDL_URL, LidlParksideProvider.id, START)  # type: ignore[arg-type]


def test_parser_wraps_domain_validation_error() -> None:
    with pytest.raises(LidlProductDataError, match="timezone-aware") as captured:
        parse_lidl_product(
            product_html(),
            LIDL_URL,
            LidlParksideProvider.id,
            datetime(2026, 7, 30),
        )

    assert captured.value.__cause__ is not None


def test_fetch_keeps_successes_and_reports_supported_failures_in_order() -> None:
    third_url = "https://www.lidl.cz/p/parkside-performance-pila/p100382711"
    client = FakeHttpClient(
        {
            LIDL_URL: HttpClientError("offline"),
            SECOND_LIDL_URL: "<html>no product</html>",
            third_url: product_html(product_data(sku="100382711")),
        }
    )

    result = _provider(client, urls=(LIDL_URL, SECOND_LIDL_URL, third_url)).fetch()

    assert [product.id for product in result.products] == [
        ProductId(uuid5(LidlParksideProvider.id.value, "100382711"))
    ]
    assert len(result.errors) == 2
    assert all(isinstance(error, ProviderError) for error in result.errors)
    assert LIDL_URL in str(result.errors[0])
    assert "offline" in str(result.errors[0])
    assert SECOND_LIDL_URL in str(result.errors[1])
    assert client.requested_urls == [LIDL_URL, SECOND_LIDL_URL, third_url]


def test_fetch_preserves_configured_product_order() -> None:
    first_html = product_html(product_data(sku="first"))
    second_html = product_html(product_data(sku="second"))
    client = FakeHttpClient({LIDL_URL: first_html, SECOND_LIDL_URL: second_html})

    result = _provider(client, urls=(LIDL_URL, SECOND_LIDL_URL)).fetch()

    assert [product.id for product in result.products] == [
        ProductId(uuid5(LidlParksideProvider.id.value, "first")),
        ProductId(uuid5(LidlParksideProvider.id.value, "second")),
    ]


def test_fetch_does_not_hide_unexpected_failure() -> None:
    failure = RuntimeError("programming error")
    client = FakeHttpClient({LIDL_URL: failure})

    with pytest.raises(RuntimeError) as captured:
        _provider(client).fetch()

    assert captured.value is failure


@pytest.mark.parametrize(
    "urls",
    [
        [LIDL_URL],
        (LIDL_URL, 4),
    ],
)
def test_constructor_rejects_invalid_product_url_collection_type(urls: object) -> None:
    with pytest.raises(TypeError, match="tuple of strings"):
        _provider(FakeHttpClient({}), urls=urls)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("urls", "message"),
    [
        ((), "empty"),
        ((LIDL_URL, LIDL_URL), "unique"),
        (("http://www.lidl.cz/p/tool/p1",), "HTTPS"),
        (("https://example.cz/p/tool/p1",), "Lidl"),
        (("https://www.lidl.cz/search",), "individual product"),
    ],
)
def test_constructor_rejects_invalid_product_url_values(
    urls: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _provider(FakeHttpClient({}), urls=urls)


@pytest.mark.parametrize("client", [object(), type("Client", (), {"get": None})()])
def test_constructor_rejects_client_without_callable_get(client: object) -> None:
    with pytest.raises(TypeError, match="http_client"):
        _provider(client)


def test_constructor_rejects_non_callable_clock() -> None:
    with pytest.raises(TypeError, match="clock"):
        _provider(FakeHttpClient({}), clock=object())


def test_fetch_rejects_non_datetime_clock_value() -> None:
    with pytest.raises(TypeError, match="return a datetime"):
        _provider(FakeHttpClient({}), clock=static_clock("now")).fetch()  # type: ignore[arg-type]


def test_fetch_rejects_naive_clock_value() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _provider(
            FakeHttpClient({}),
            clock=static_clock(datetime(2026, 7, 30)),
        ).fetch()


def test_fetch_rejects_clock_moving_backwards() -> None:
    client = FakeHttpClient({LIDL_URL: product_html()})

    with pytest.raises(ValueError, match="before start"):
        _provider(client, clock=sequence_clock(FINISH, START)).fetch()
