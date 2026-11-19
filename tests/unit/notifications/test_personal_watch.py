"""Personal selection, target freshness and category rules."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from core.domain import Money, Currency, Percentage
from core.watch import DigestWatchPreferences, DigestWatchPolicy, WatchProductPreference, WatchCategoryRule, WatchTargetStatus as Status
from core.notifications import DailyDiscountDigestEngine, DigestFreshnessPolicy
from core.state import StateSnapshot
from tests.unit.pricing.test_price_history import NOW
from tests.unit.notifications.test_daily_digest import _product


def product(identifier=1, *, name="Tool", price="80", reference="100", discount="20", available=True):
    return replace(_product(identifier, name, discount, available=available, reference=reference), current_price=Money(Decimal(price), Currency.CZK))


def test_hidden_wins_and_watches_override_category_and_discount() -> None:
    favorite = product(reference=None, discount="0")
    rule = WatchCategoryRule("zahrada", ("sekačka",))
    preferences = DigestWatchPreferences((WatchProductPreference(favorite.id, favorite=True),), (rule,), ("zahrada",))
    policy = DigestWatchPolicy(preferences)
    assert policy.selected(favorite, Percentage(Decimal(20)))
    assert not policy.selected(product(2), Percentage(Decimal(20)))
    assert not policy.selected(replace(favorite, availability=False), Percentage(Decimal(20)))
    hidden = replace(preferences, product_rules=(WatchProductPreference(favorite.id, True, Money(Decimal(100), Currency.CZK), True),))
    assert not DigestWatchPolicy(hidden).selected(favorite, Percentage(Decimal(20)))


def test_categories_match_complete_normalized_phrases_and_filters_are_or() -> None:
    categories = (WatchCategoryRule("zahrada", ("řetězová pila",)), WatchCategoryRule("prislusenstvi", ("sada bitů",)))
    policy = DigestWatchPolicy(DigestWatchPreferences((), categories, ("zahrada", "prislusenstvi")))
    saw = product(name="PARKSIDE AKU RETEZOVA   PILA")
    assert policy.categories(saw) == ("zahrada",)
    assert policy.selected(saw, Percentage(Decimal(20)))
    assert policy.selected(product(2, name="Sada bitů"), Percentage(Decimal(20)))
    assert policy.categories(product(name="řetězová pilarka")) == ("ostatni",)
    assert not policy.selected(product(name="řetězová pilarka"), Percentage(Decimal(20)))
    assert not policy.selected(product(name="Sada bitů", reference=None), Percentage(Decimal(20)))


@pytest.mark.parametrize(("age", "amount", "currency", "expected"), [
    (timedelta(), "80", Currency.CZK, Status.REACHED),
    (timedelta(), "79.99", Currency.CZK, Status.WAITING),
    (timedelta(hours=1), "80", Currency.CZK, Status.REACHED),
    (timedelta(hours=1, seconds=1), "80", Currency.CZK, Status.UNVERIFIED),
    (timedelta(seconds=-1), "80", Currency.CZK, Status.UNVERIFIED),
    (timedelta(), "80", Currency.EUR, Status.CURRENCY_MISMATCH),
])
def test_target_requires_exact_currency_and_recent_evidence(age, amount, currency, expected) -> None:
    current = product()
    policy = DigestWatchPolicy(DigestWatchPreferences((WatchProductPreference(current.id, target_price=Money(Decimal(amount), currency)),)))
    assert policy.target_status(current, NOW - age, NOW) is expected
    assert policy.priority(current, NOW - age, NOW) == (0 if expected is Status.REACHED else 1)


def test_zero_target_unavailable_offer_and_unwatched_status() -> None:
    current = product(price="0")
    policy = DigestWatchPolicy(DigestWatchPreferences((WatchProductPreference(current.id, target_price=Money(Decimal(0), Currency.CZK)),)))
    assert policy.target_status(current, NOW, NOW) is Status.REACHED
    assert policy.target_status(replace(current, availability=False), NOW, NOW) is Status.UNVERIFIED
    ordinary = product(2)
    assert policy.target_status(ordinary, NOW, NOW) is Status.NONE
    assert policy.priority(ordinary, NOW, NOW) == 2


def test_personal_digest_groups_targets_and_favorites_without_claiming_every_item_discounted() -> None:
    hit, favorite, ordinary = product(1), product(2, reference=None, discount="0"), product(3)
    preferences = DigestWatchPreferences((WatchProductPreference(hit.id, target_price=Money(Decimal(80), Currency.CZK)), WatchProductPreference(favorite.id, True)))
    snapshots = tuple(StateSnapshot(p, NOW) for p in (ordinary, favorite, hit))
    digest = DailyDiscountDigestEngine().generate(snapshots, Percentage(Decimal(20)), NOW.date(), NOW,
        previous_product_ids=(), watch_preferences=preferences)
    assert digest.products[:2] == (hit, favorite)
    assert set(digest.baseline_product_ids) == {hit.id, ordinary.id}
    assert favorite.id not in digest.new_product_ids
    assert "DOSAŽENÉ CÍLOVÉ CENY" in digest.message
    assert "OBLÍBENÉ A HLÍDANÉ PRODUKTY" in digest.message
    assert "Nabídky v osobním přehledu: 3" in digest.message
    assert "Reference price: neuvedena" in digest.message


def test_inactive_defaults_preserve_output_and_empty_filter_explains_selection() -> None:
    engine = DailyDiscountDigestEngine()
    snapshot = StateSnapshot(product(), NOW)
    args = ((snapshot,), Percentage(Decimal(20)), NOW.date(), NOW)
    assert engine.generate(*args).message == engine.generate(*args, watch_preferences=DigestWatchPreferences()).message
    hidden = DigestWatchPreferences((WatchProductPreference(snapshot.product.id, hidden=True),))
    assert "neodpovídají osobnímu výběru" in engine.generate(*args, watch_preferences=hidden).message


def test_refresh_prioritizes_explicit_watches_and_excludes_hidden() -> None:
    ordinary, favorite, hidden = product(1), product(2, reference=None, discount="0"), product(3)
    preferences = DigestWatchPreferences((WatchProductPreference(favorite.id, True), WatchProductPreference(hidden.id, hidden=True)))
    snapshots = (StateSnapshot(ordinary, NOW - timedelta(days=10)), StateSnapshot(favorite, NOW - timedelta(days=1)), StateSnapshot(hidden, NOW - timedelta(days=20)))
    assert DigestFreshnessPolicy().select(snapshots, Percentage(Decimal(20)), NOW, limit=1, watch_preferences=preferences) == (favorite,)


@pytest.mark.parametrize("value", [object(), "preferences"])
def test_policy_requires_validated_preferences(value) -> None:
    with pytest.raises(TypeError):
        DigestWatchPolicy(value)


@pytest.mark.parametrize("changes, error", [
    ({"product_id": "bad"}, TypeError), ({"favorite": 1}, TypeError),
    ({"hidden": 1}, TypeError), ({"target_price": "80"}, TypeError),
    ({"favorite": False}, ValueError),
])
def test_product_preference_rejects_invalid_choices(changes, error) -> None:
    values = {"product_id": product().id, "favorite": True, **changes}
    with pytest.raises(error):
        WatchProductPreference(**values)


@pytest.mark.parametrize("name, keywords, error", [
    (None, ("tool",), ValueError), ("Bad name", ("tool",), ValueError),
    ("ostatni", ("tool",), ValueError), ("tools", ["tool"], TypeError),
    ("tools", (1,), TypeError), ("tools", (), ValueError),
    ("tools", ("!!!",), ValueError),
])
def test_category_rejects_ambiguous_or_empty_rules(name, keywords, error) -> None:
    with pytest.raises(error):
        WatchCategoryRule(name, keywords)


@pytest.mark.parametrize("changes, error", [
    ({"product_rules": []}, TypeError), ({"product_rules": (object(),)}, TypeError),
    ({"category_rules": []}, TypeError), ({"category_rules": (object(),)}, TypeError),
    ({"included_categories": []}, TypeError), ({"included_categories": (1,)}, TypeError),
    ({"product_rules": (WatchProductPreference(product().id, True),) * 2}, ValueError),
    ({"category_rules": (WatchCategoryRule("tools", ("tool",)),) * 2}, ValueError),
    ({"included_categories": ("ostatni", "ostatni")}, ValueError),
    ({"included_categories": ("unknown",)}, ValueError),
])
def test_preferences_reject_invalid_or_duplicate_collections(changes, error) -> None:
    with pytest.raises(error):
        DigestWatchPreferences(**changes)


def test_policy_rejects_invalid_product_discount_and_timestamps() -> None:
    policy = DigestWatchPolicy(DigestWatchPreferences())
    with pytest.raises(TypeError):
        policy.preference(object())
    with pytest.raises(TypeError):
        policy.selected(product(), 20)
    for invalid, error in ((object(), TypeError), (NOW.replace(tzinfo=None), ValueError)):
        with pytest.raises(error):
            policy.target_status(product(), invalid, NOW)
        with pytest.raises(error):
            policy.target_status(product(), NOW, invalid)


def test_digest_rejects_unresolved_preferences_and_invalid_baseline() -> None:
    engine = DailyDiscountDigestEngine()
    snapshot = StateSnapshot(product(), NOW)
    args = ((snapshot,), Percentage(Decimal(20)), NOW.date(), NOW)
    with pytest.raises(TypeError):
        engine.generate(*args, watch_preferences=object())
    with pytest.raises(ValueError, match="resolve"):
        engine.generate(*args, watch_preferences=DigestWatchPreferences((WatchProductPreference(product(99).id, True),)))
    digest = engine.generate(*args)
    with pytest.raises(TypeError):
        replace(digest, watch_preferences=object())
    with pytest.raises(ValueError):
        replace(digest, baseline_product_ids=(product(99).id,))
    with pytest.raises(TypeError):
        replace(digest, baseline_product_ids=[])


@pytest.mark.parametrize("age, currency, expected", [
    (timedelta(), Currency.CZK, "čekáme na cílovou cenu"),
    (timedelta(days=1), Currency.CZK, "neověřeno"),
    (timedelta(), Currency.EUR, "jiná měna"),
])
def test_digest_explains_waiting_stale_and_incomparable_targets(age, currency, expected) -> None:
    current = product()
    preference = WatchProductPreference(current.id, target_price=Money(Decimal(70), currency))
    digest = DailyDiscountDigestEngine().generate((StateSnapshot(current, NOW - age),), Percentage(Decimal(20)), NOW.date(), NOW,
        watch_preferences=DigestWatchPreferences((preference,)))
    assert expected in digest.message
    assert "DOSAŽENÉ CÍLOVÉ CENY" not in digest.message


def test_personal_groups_distinguish_new_and_remaining_ordinary_discounts() -> None:
    new, old = product(1), product(2)
    digest = DailyDiscountDigestEngine().generate(tuple(StateSnapshot(p, NOW) for p in (new, old)), Percentage(Decimal(20)), NOW.date(), NOW,
        previous_product_ids=(old.id,), watch_preferences=DigestWatchPreferences(included_categories=("ostatni",)))
    assert "NOVĚ V OSOBNÍM VÝBĚRU SLEV" in digest.message
    assert "OSTATNÍ AKTUÁLNÍ SLEVY" in digest.message


def test_more_than_two_hundred_watches_still_respect_refresh_budget() -> None:
    products = tuple(product(i, reference=None, discount="0") for i in range(1, 203))
    preferences = DigestWatchPreferences(tuple(WatchProductPreference(p.id, True) for p in products))
    snapshots = tuple(StateSnapshot(p, NOW - timedelta(days=1, minutes=i)) for i, p in enumerate(products))
    selected = DigestFreshnessPolicy().select(snapshots, Percentage(Decimal(20)), NOW, watch_preferences=preferences)
    assert len(selected) == 200
    assert selected[0] == products[-1] and selected[-1] == products[2]
