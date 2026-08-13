"""Tests for provider-neutral daily promotion contracts."""

import inspect
from typing import cast

import pytest

import core.promotions as promotions_api
from core.promotions import DailyPromotion, DailyPromotionSource, PromotionError


class _Source:
    def current(self) -> DailyPromotion | None:
        return DailyPromotion("Offer", "https://example.test/offer")


def test_daily_promotion_is_immutable_and_accepts_optional_https_url() -> None:
    promotion = DailyPromotion("Today only", "https://example.test/offer")

    assert promotion.url == "https://example.test/offer"
    assert DailyPromotion("Today only").url is None
    with pytest.raises(AttributeError):
        promotion.text = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("values", "error", "message"),
    [
        ((1,), TypeError, "text"),
        (("  ",), ValueError, "blank"),
        (("Offer", 1), TypeError, "url"),
        (("Offer", ""), ValueError, "HTTPS"),
        (("Offer", "/offer"), ValueError, "HTTPS"),
        (("Offer", "http://example.test"), ValueError, "HTTPS"),
    ],
)
def test_daily_promotion_rejects_invalid_values(
    values: tuple[object, ...],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        DailyPromotion(*cast(tuple, values))


def test_public_api_is_explicit_documented_and_protocol_compatible() -> None:
    assert promotions_api.__all__ == [
        "DailyPromotion",
        "DailyPromotionSource",
        "PromotionError",
    ]
    source: DailyPromotionSource = _Source()
    assert source.current() == DailyPromotion(
        "Offer",
        "https://example.test/offer",
    )
    assert isinstance(PromotionError("failed"), Exception)
    for public_object in (DailyPromotion, DailyPromotionSource, PromotionError):
        assert inspect.getdoc(public_object)
    assert inspect.getdoc(DailyPromotionSource.current)
