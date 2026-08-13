"""Tests for the Lidl Czech Republic marketing-promotion source."""

from typing import cast

import pytest

from core.promotions import DailyPromotion, PromotionError
from infrastructure.http import HttpClientError, TextHttpClient
from infrastructure.providers.lidl import LidlMarketingPromotionSource

_HOME_PAGE = "https://www.lidl.cz/"


class _Client:
    def __init__(self, payload: object = "", error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.urls: list[str] = []

    def get(self, url: str) -> str:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return cast(str, self.payload)


def _source(payload: object) -> tuple[LidlMarketingPromotionSource, _Client]:
    client = _Client(payload)
    return LidlMarketingPromotionSource(cast(TextHttpClient, client)), client


def test_source_parses_current_markup_entities_nested_text_and_whitespace() -> None:
    source, client = _source(
        '<a href="https://www.lidl.cz/c/doprava/s1">'
        '<span class="other n-navigation__marketing-message--label">'
        " Online&nbsp; | <strong>Pouze dnes</strong> &amp; doprava zdarma "
        "</span></a>"
    )

    assert source.current() == DailyPromotion(
        "Online | Pouze dnes & doprava zdarma",
        "https://www.lidl.cz/c/doprava/s1",
    )
    assert client.urls == [_HOME_PAGE]


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("/c/offer/s1", "https://www.lidl.cz/c/offer/s1"),
        ("https://lidl.cz/c/offer/s1", "https://lidl.cz/c/offer/s1"),
        ("https://www.lidl.cz:443/c/offer", "https://www.lidl.cz:443/c/offer"),
    ],
)
def test_source_accepts_safe_absolute_and_relative_lidl_links(
    href: str,
    expected: str,
) -> None:
    source, _ = _source(
        f'<a href="{href}"><span class="n-navigation__marketing-message--label">'
        "Offer</span></a>"
    )

    assert source.current() == DailyPromotion("Offer", expected)


def test_source_uses_first_message_and_accepts_missing_link_or_label() -> None:
    source, _ = _source(
        '<span class="n-navigation__marketing-message--label">First</span>'
        '<span class="n-navigation__marketing-message--label">Second</span>'
    )
    missing, _ = _source('<a href="/offer"><span>ordinary</span></a>')

    assert source.current() == DailyPromotion("First")
    assert missing.current() is None


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ('<span class="n-navigation__marketing-message--label"> </span>', "invalid"),
        ('<span class="n-navigation__marketing-message--label">unfinished', "invalid"),
        (
            '<a href="/offer"><span class="n-navigation__marketing-message--label">'
            "unfinished</a>",
            "invalid",
        ),
        (
            '<a href="http://www.lidl.cz/offer">'
            '<span class="n-navigation__marketing-message--label">Offer</span></a>',
            "invalid",
        ),
        (
            '<a href="https://example.test/offer">'
            '<span class="n-navigation__marketing-message--label">Offer</span></a>',
            "invalid",
        ),
        (
            '<a href="https://user@www.lidl.cz/offer">'
            '<span class="n-navigation__marketing-message--label">Offer</span></a>',
            "invalid",
        ),
        (
            '<a href="https://www.lidl.cz:444/offer">'
            '<span class="n-navigation__marketing-message--label">Offer</span></a>',
            "invalid",
        ),
        (
            '<a href="https://www.lidl.cz:bad/offer">'
            '<span class="n-navigation__marketing-message--label">Offer</span></a>',
            "invalid",
        ),
        (
            '<a href=" "><span class="n-navigation__marketing-message--label">'
            "Offer</span></a>",
            "invalid",
        ),
    ],
)
def test_source_rejects_malformed_or_unsafe_banner_data(
    payload: object,
    message: str,
) -> None:
    source, _ = _source(payload)

    with pytest.raises(PromotionError, match=message):
        source.current()


def test_source_maps_non_text_and_http_failures() -> None:
    non_text, _ = _source(b"html")
    failure = HttpClientError("offline")
    source = LidlMarketingPromotionSource(
        cast(TextHttpClient, _Client(error=failure))
    )

    with pytest.raises(PromotionError, match="must be text"):
        non_text.current()
    with pytest.raises(PromotionError, match="retrieve") as captured:
        source.current()
    assert captured.value.__cause__ is failure


def test_source_rejects_invalid_http_dependency() -> None:
    with pytest.raises(TypeError, match="http_client"):
        LidlMarketingPromotionSource(cast(TextHttpClient, object()))
