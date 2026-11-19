"""Stable Lidl product-link identity and pure option validation."""

from dataclasses import replace
from decimal import Decimal

import pytest

from core.domain import Money, Currency
from core.state import StateSnapshot
from core.watch import WatchCategoryRule
from infrastructure.providers.lidl import LidlWatchPreferenceSource, LidlParksideProvider
from tests.unit.notifications.test_personal_watch import product
from tests.unit.pricing.test_price_history import NOW

URL = "https://www.lidl.cz/p/parkside-tool/p100123"


def test_resolver_matches_changed_slug_and_tracking_and_seeds_only_nonhidden() -> None:
    source = LidlWatchPreferenceSource((URL + "?campaign=one#top",), (), ((URL, Money(Decimal(80), Currency.CZK)),))
    current = replace(product(), provider_id=LidlParksideProvider.id, url="https://lidl.cz/p/parkside-new-name/p100123")
    preferences = source.resolve((StateSnapshot(current, NOW),))
    assert preferences.product_rules[0].favorite
    assert preferences.product_rules[0].target_price.amount == Decimal(80)
    assert source.seed_references()[0].external_id == "p100123"
    assert "?" not in source.seed_references()[0].url
    hidden = LidlWatchPreferenceSource((URL,), (URL,))
    assert hidden.seed_references() == ()
    assert hidden.resolve((StateSnapshot(current, NOW),)).product_rules[0].hidden
    assert source.resolve((StateSnapshot(product(), NOW),)).product_rules == ()
    unrelated = replace(current, url="https://www.lidl.cz/p/other/p100456")
    assert source.resolve((StateSnapshot(unrelated, NOW),)).product_rules == ()


@pytest.mark.parametrize("url", [
    "http://www.lidl.cz/p/tool/p100123", "https://evil.test/p/tool/p100123",
    "https://www.lidl.cz/search", "https://user@www.lidl.cz/p/tool/p100123",
    "https://www.lidl.cz:444/p/tool/p100123", "https://www.lidl.cz:bad/p/tool/p100123",
])
def test_invalid_watch_links_are_rejected(url) -> None:
    with pytest.raises(ValueError):
        LidlWatchPreferenceSource((url,))


def test_duplicate_links_and_invalid_collections_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        LidlWatchPreferenceSource((URL, URL + "?tracking=1"))
    with pytest.raises(TypeError):
        LidlWatchPreferenceSource([URL])
    with pytest.raises(TypeError):
        LidlWatchPreferenceSource(target_prices=((URL, "80"),))
    with pytest.raises(TypeError):
        LidlWatchPreferenceSource().resolve([])
    with pytest.raises(TypeError):
        LidlWatchPreferenceSource().resolve((object(),))
    snapshot = StateSnapshot(product(), NOW)
    with pytest.raises(ValueError):
        LidlWatchPreferenceSource().resolve((snapshot, snapshot))
