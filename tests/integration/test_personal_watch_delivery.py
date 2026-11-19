"""Personal watch persistence, novelty, seed identity and one daily delivery."""

from dataclasses import replace
from datetime import time, timedelta
from decimal import Decimal

import pytest

from applications.daily_digest import DailyDigestWorkflow, DailyDigestConfig, DailyDigestStatus
from applications.catalog_monitoring import CatalogMonitoringWorkflow
from core.domain import Percentage, Money, Currency
from core.catalog import ProductReference
from core.notifications import DailyDiscountDigestEngine
from core.state import StateSnapshot
from infrastructure.persistence.sqlite import SqliteStateStore, SqliteCatalogStore, SqliteDigestDeliveryStore, SqliteDailyDigestReservationStore, SqliteDailyDigestBaselineStore, SqlitePriceHistoryAssessmentSource
from infrastructure.providers.lidl import LidlParksideProvider, LidlWatchPreferenceSource
from tests.unit.daily_digest.test_workflow import _Channel, _PromotionSource
from core.promotions import PromotionError
from tests.unit.catalog_monitoring.test_workflow import _Catalog, _Synchronizer
from tests.unit.notifications.test_personal_watch import product
from tests.unit.pricing.test_price_history import NOW, PRAGUE
from tests.unit.providers.test_watch_preferences import URL


def test_nonsale_favorite_does_not_suppress_later_sale_novelty_or_duplicate_delivery(tmp_path) -> None:
    path, channel = tmp_path / "db", _Channel()
    store = SqliteStateStore(path)
    current = replace(product(reference=None, discount="0", price="100"), provider_id=LidlParksideProvider.id, url=URL)
    store.save(StateSnapshot(current, NOW))
    preference_source = LidlWatchPreferenceSource((URL,), target_prices=((URL, Money(Decimal(90), Currency.CZK)),))
    def build():
        return DailyDigestWorkflow(store, SqliteDailyDigestReservationStore(path), DailyDiscountDigestEngine(), channel,
            DailyDigestConfig(time(8), Percentage(Decimal(20))), PRAGUE, baseline_store=SqliteDailyDigestBaselineStore(path),
            delivery_store=SqliteDigestDeliveryStore(path), watch_preference_source=preference_source,
            price_history_source=SqlitePriceHistoryAssessmentSource(path, PRAGUE))
    assert build().run(NOW).status is DailyDigestStatus.SENT
    assert channel.digests[0].products == (current,)
    assert channel.digests[0].baseline_product_ids == ()
    assert "čekáme na cílovou cenu" in channel.digests[0].message
    assert SqliteDailyDigestBaselineStore(path).previous_product_ids(NOW.date() + timedelta(days=1)) == ()
    later = NOW + timedelta(days=1)
    sale = replace(current, current_price=Money(Decimal(80), Currency.CZK), original_price=Money(Decimal(100), Currency.CZK), discount_percent=Percentage(Decimal(20)))
    store.save(StateSnapshot(sale, later))
    assert build().run(later).status is DailyDigestStatus.SENT
    assert channel.digests[1].new_product_ids == (current.id,)
    assert "DOSAŽENÉ CÍLOVÉ CENY" in channel.digests[1].message
    assert channel.digests[1].price_assessments
    assert build().run(later + timedelta(minutes=5)).status is DailyDigestStatus.ALREADY_SENT
    assert len(channel.digests) == 2
    assert len(store.history(current.id)) == 2


def test_explicit_watch_is_seeded_once_without_overwriting_newer_catalog_url(tmp_path) -> None:
    path = tmp_path / "db"
    store = SqliteCatalogStore(path)
    source = LidlWatchPreferenceSource((URL,))
    calls = []
    workflow = CatalogMonitoringWorkflow(_Catalog(calls), store, store, _Synchronizer(calls), LidlParksideProvider.id, 25, seed_references=source.seed_references())
    first = workflow.run((), NOW, False)
    assert len(first.new_references) == 1 and first.refresh_references[0].url == URL
    canonical = ProductReference(LidlParksideProvider.id, "p100123", "https://www.lidl.cz/p/parkside-updated/p100123")
    store.record_discovery((canonical,), NOW + timedelta(minutes=1))
    second = workflow.run((), NOW + timedelta(minutes=2), False)
    assert second.new_references == ()
    assert second.refresh_references == (canonical,)
    assert store.list_entries(LidlParksideProvider.id)[0].reference.url == canonical.url


def test_seed_validation_and_discovery_merge(tmp_path) -> None:
    store, calls = SqliteCatalogStore(tmp_path / "db"), []
    seed = LidlWatchPreferenceSource((URL,)).seed_references()[0]
    other = replace(seed, external_id="p100456", url="https://www.lidl.cz/p/tool/p100456")
    def build(seeds):
        return CatalogMonitoringWorkflow(_Catalog(calls, (seed, other)), store, store, _Synchronizer(calls), LidlParksideProvider.id, 25, seed_references=seeds)
    for invalid in ([], (object(),)):
        with pytest.raises(TypeError):
            build(invalid)
    with pytest.raises(ValueError):
        build((seed, seed))
    with pytest.raises(ValueError):
        build((replace(seed, provider_id=product().provider_id),))
    result = build((seed,)).run((), NOW)
    assert result.new_references == (seed, other)
    assert result.discovered_references == (seed, other)


def test_personal_preferences_survive_banner_fallback_and_failed_preparation(tmp_path) -> None:
    path, channel = tmp_path / "db", _Channel()
    store = SqliteStateStore(path)
    favorite = replace(product(reference=None, discount="0"), provider_id=LidlParksideProvider.id, url=URL)
    store.save(StateSnapshot(favorite, NOW))
    promotion = _PromotionSource()
    promotion.error = PromotionError("banner offline")
    class Source:
        broken = True
        def resolve(self, snapshots):
            if self.broken:
                raise ValueError("invalid preferences")
            return LidlWatchPreferenceSource((URL,)).resolve(snapshots)
    source = Source()
    def build():
        return DailyDigestWorkflow(store, SqliteDailyDigestReservationStore(path), DailyDiscountDigestEngine(), channel,
            DailyDigestConfig(time(8), Percentage(Decimal(20))), PRAGUE, baseline_store=SqliteDailyDigestBaselineStore(path),
            delivery_store=SqliteDigestDeliveryStore(path), watch_preference_source=source, promotion_source=promotion)
    later = NOW + timedelta(hours=1)
    with pytest.raises(ValueError, match="invalid preferences"):
        build().run(later)
    assert channel.digests == []
    source.broken = False
    result = build().run(later)
    assert result.status is DailyDigestStatus.SENT and result.promotion_missing
    assert channel.digests[0].products == (favorite,)
    assert channel.digests[0].watch_preferences.product_rules[0].favorite
    assert channel.digests[0].baseline_product_ids == ()
    assert build().run(later + timedelta(minutes=5)).status is DailyDigestStatus.ALREADY_SENT
