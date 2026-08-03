"""Tests for concrete Home Assistant catalog monitoring composition."""

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from applications.catalog_monitoring import (
    CatalogMonitoringConfig,
    CatalogMonitoringWorkflow,
)
from applications.homeassistant import HomeAssistantConfig
from applications.homeassistant.composition import (
    _HomeAssistantComposition,
    _LidlCatalogBatchSynchronizer,
    _compose_homeassistant,
)
from core.catalog import ProductReference
from core.domain import ProviderId, Rule, RuleType
from core.notifications import NotificationEngine
from core.rules import EvaluatorRegistry, RuleEngine
from core.rules.evaluators import BackInStockEvaluator
from infrastructure.notifications.homeassistant import HomeAssistantNotificationChannel
from infrastructure.persistence.memory import InMemoryStateStore
from infrastructure.persistence.sqlite import SqliteCatalogStore, SqliteStateStore
from infrastructure.providers.lidl import LidlParksideCatalog
from tests.unit.homeassistant_app.helpers import TIMESTAMP


class _TextClient:
    def get(self, url: str) -> str:
        document = {
            "@context": "https://schema.org",
            "@type": "Product",
            "sku": "123456",
            "brand": {"@type": "Brand", "name": "PARKSIDE"},
            "name": "Parkside Test Tool",
            "offers": {
                "@type": "Offer",
                "price": "999.90",
                "priceCurrency": "CZK",
                "availability": "https://schema.org/InStock",
            },
        }
        return f'<script type="application/ld+json">{json.dumps(document)}</script>'


class _Channel:
    def send(self, notification: object) -> None:
        return None


def _catalog_config() -> HomeAssistantConfig:
    return HomeAssistantConfig(
        application=None,
        catalog=CatalogMonitoringConfig(
            database_file=Path("/data/catalog.sqlite3"),
            interval=timedelta(seconds=300),
            timeout_seconds=12,
            batch_size=30,
            discovery_interval_cycles=48,
            price_drop_percentage=Decimal("20.00"),
        ),
        notify_entity="notify.gmail_parkside",
        notification_title="Parkside Catalog",
    )


def test_catalog_composition_assembles_shared_sqlite_stack() -> None:
    config = _catalog_config()

    result = _compose_homeassistant(config, "token", lambda: TIMESTAMP, uuid4)

    assert result.workflow is None
    assert isinstance(result.catalog_workflow, CatalogMonitoringWorkflow)
    assert result.interval == timedelta(seconds=300)
    assert result.discovery_interval_cycles == 48
    assert dict(result.rules[0].parameters) == {"percentage": Decimal("20.00")}
    workflow = result.catalog_workflow
    assert isinstance(workflow._catalog, LidlParksideCatalog)
    assert isinstance(workflow._catalog_store, SqliteCatalogStore)
    assert workflow._catalog_store is workflow._refresh_store
    assert workflow._catalog_store._database._path == Path(
        "/data/catalog.sqlite3"
    )
    assert workflow._batch_size == 30
    synchronizer = workflow._batch_synchronizer
    assert isinstance(synchronizer, _LidlCatalogBatchSynchronizer)
    assert isinstance(synchronizer._state_store, SqliteStateStore)
    assert synchronizer._state_store._database._path == Path(
        "/data/catalog.sqlite3"
    )
    assert synchronizer._http_client._timeout_seconds == 12
    channel = synchronizer._notification_channel
    assert isinstance(channel, HomeAssistantNotificationChannel)
    assert channel._entity_id == "notify.gmail_parkside"
    assert channel._title == "Parkside Catalog"


def test_batch_synchronizer_reuses_standard_workflow() -> None:
    registry = EvaluatorRegistry()
    registry.register(BackInStockEvaluator())
    store = InMemoryStateStore()
    synchronizer = _LidlCatalogBatchSynchronizer(
        cast(object, _TextClient()),
        lambda: TIMESTAMP,
        store,
        RuleEngine(registry),
        NotificationEngine(),
        cast(object, _Channel()),
        lambda: UUID("90000000-0000-4000-8000-000000000001"),
    )
    reference = ProductReference(
        ProviderId(UUID("018f0000-0000-7000-8000-000000000020")),
        "p100",
        "https://www.lidl.cz/p/parkside-test-tool/p100",
    )
    rule = Rule(
        UUID("70000000-0000-4000-8000-000000000002"),
        "stock",
        True,
        RuleType.BACK_IN_STOCK,
    )

    result = synchronizer.synchronize((reference,), (rule,), TIMESTAMP)

    assert len(result.fetch_results) == 1
    assert len(result.snapshots) == 1
    assert result.snapshots[0].product.name == "Parkside Test Tool"


def test_composition_dataclass_requires_exactly_one_workflow() -> None:
    explicit = _compose_homeassistant(
        HomeAssistantConfig(
            application=None,
            catalog=CatalogMonitoringConfig(
                Path("catalog.sqlite3"),
                timedelta(minutes=5),
            ),
            notify_entity="notify.gmail_parkside",
        ),
        "token",
        lambda: TIMESTAMP,
        uuid4,
    )

    with pytest.raises(ValueError, match="exactly one"):
        _HomeAssistantComposition(
            workflow=None,
            catalog_workflow=None,
            status_publisher=explicit.status_publisher,
            rules=explicit.rules,
            interval=explicit.interval,
        )


def test_composition_defends_against_missing_mode_after_validation() -> None:
    config = _catalog_config()
    object.__setattr__(config, "catalog", None)

    with pytest.raises(ValueError, match="configuration"):
        _compose_homeassistant(config, "token", lambda: TIMESTAMP, uuid4)
