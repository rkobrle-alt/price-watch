"""Persistent retry scheduling, filtering and recovery across process restarts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from applications.catalog_monitoring import PageAwareSnapshotReader, ProductPageTracker, CatalogMonitoringWorkflow
from core.catalog import CatalogEntry, MissingPagePolicy, MissingProductPage
from core.provider import ProviderProductNotFoundError, ProviderTransportError
from infrastructure.persistence.sqlite import SqliteMissingProductPageStore, SqliteStateStore
from tests.unit.notifications.test_daily_digest import _product
from core.state import StateSnapshot
from tests.unit.catalog_monitoring.test_workflow import _Catalog, _Store, _Synchronizer
from tests.unit.persistence.sqlite_helpers import CATALOG_PROVIDER_ID, OTHER_PROVIDER_ID, create_reference

NOW = datetime(2026, 11, 19, 7, tzinfo=UTC)


def test_lifecycle_retains_history_excludes_missing_and_recovers(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    product = _product(1, "Tool", "20")
    state = SqliteStateStore(path)
    state.save(StateSnapshot(product, NOW))
    store = SqliteMissingProductPageStore(path)
    tracker = ProductPageTracker(store)
    error = ProviderProductNotFoundError("404", product.url)
    for index, hours in enumerate((6, 24, 168, 168), 1):
        tracker.record(product.provider_id, (), (error,), NOW + timedelta(days=index))
        page = SqliteMissingProductPageStore(path).load()[0]
        assert page.failures == index
        assert page.retry_at - page.checked_at == timedelta(hours=hours)
    reader = PageAwareSnapshotReader(state, store)
    assert reader.latest_snapshots() == ()
    assert len(state.history(product.id)) == 1
    tracker.record(product.provider_id, (), (ProviderTransportError("timeout"),), NOW + timedelta(days=5))
    assert store.load() == (page,)
    tracker.record(product.provider_id, (product,), (), NOW + timedelta(days=6))
    assert store.load() == ()
    assert reader.latest_snapshots() == (StateSnapshot(product, NOW),)


def test_selection_skips_sleeping_pages_without_starving_eligible_urls(tmp_path: Path) -> None:
    store = SqliteMissingProductPageStore(tmp_path / "catalog.sqlite3")
    first, second, third = (create_reference(f"p{i}") for i in range(3))
    page = MissingPagePolicy().record(CATALOG_PROVIDER_ID, first.url, NOW)
    store.save((page, MissingPagePolicy().record(OTHER_PROVIDER_ID, second.url, NOW)))
    calls = []

    class Entries(_Store):
        def list_entries(self, provider_id):
            return tuple(CatalogEntry(r, NOW, NOW) for r in (first, second, third))

    catalog_store = Entries(calls, refresh_references=(first, second, third))
    workflow = CatalogMonitoringWorkflow(_Catalog(calls), catalog_store, catalog_store,
        _Synchronizer(calls), CATALOG_PROVIDER_ID, 1, missing_page_store=store)
    assert workflow.run((), NOW, False).refresh_references == (second,)
    assert workflow.run((), page.retry_at, False).refresh_references == (first,)
    catalog_store.refresh_references = (first,)
    assert workflow.run((), NOW, False).refresh_references == ()


@pytest.mark.parametrize(("field", "value", "exception"), [
    ("provider_id", "x", TypeError), ("url", 1, TypeError), ("url", " ", ValueError),
    ("failures", True, TypeError), ("failures", 0, ValueError),
    ("checked_at", "now", TypeError), ("checked_at", datetime(2026, 1, 1), ValueError),
    ("retry_at", NOW, ValueError),
])
def test_missing_page_validates_evidence(field, value, exception) -> None:
    values = dict(provider_id=CATALOG_PROVIDER_ID, url="url", failures=1, checked_at=NOW, retry_at=NOW + timedelta(hours=6))
    values[field] = value
    with pytest.raises(exception):
        MissingProductPage(**values)


def test_policy_rejects_wrong_identity_time_and_previous() -> None:
    policy = MissingPagePolicy()
    page = policy.record(CATALOG_PROVIDER_ID, "url", NOW)
    with pytest.raises(TypeError):
        policy.record(CATALOG_PROVIDER_ID, "url", NOW, object())
    with pytest.raises(ValueError, match="identity"):
        policy.record(OTHER_PROVIDER_ID, "url", NOW, page)
    with pytest.raises(ValueError, match="precede"):
        policy.record(CATALOG_PROVIDER_ID, "url", NOW - timedelta(seconds=1), page)
