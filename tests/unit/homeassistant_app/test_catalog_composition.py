"""Tests for concrete Home Assistant catalog monitoring composition."""

import json
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from applications.catalog_monitoring import (
    CatalogMonitoringConfig,
    CatalogMonitoringWorkflow,
)
from applications.daily_digest import DailyDigestConfig, DailyDigestWorkflow
from applications.homeassistant import HomeAssistantConfig
from applications.homeassistant.composition import (
    _HomeAssistantComposition,
    _LidlCatalogBatchSynchronizer,
    _MaintenanceStatusComposition,
    _StorageStatusComposition,
    _compose_homeassistant,
)
from core.catalog import ProductReference
from core.domain import Percentage, ProviderId, Rule, RuleType
from core.notifications import NotificationEngine
from core.notifications import PriceDropReservationPolicy
from core.rules import EvaluatorRegistry, PriceReferencePolicy, RuleEngine
from core.rules.evaluators import BackInStockEvaluator
from infrastructure.notifications.homeassistant import (
    HomeAssistantDailyDiscountDigestChannel,
    HomeAssistantNotificationChannel,
)
from infrastructure.homeassistant import (
    HomeAssistantCatalogStatusPublisher,
    HomeAssistantMaintenanceStatusPublisher,
    HomeAssistantStorageStatusPublisher,
)
from infrastructure.persistence.memory import InMemoryStateStore
from infrastructure.persistence.sqlite import (
    SqliteCatalogStore,
    SqliteDailyDigestReservationStore,
    SqliteNotificationReservationStore,
    SqliteObservationRetentionManager,
    SqliteStateStore,
)
from infrastructure.providers.lidl import (
    LidlMarketingPromotionSource,
    LidlParksideCatalog,
)
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


def _catalog_config(
    *,
    digest: bool = False,
    individual_notifications: bool = True,
    retention_preview_days: int | None = None,
) -> HomeAssistantConfig:
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
        daily_digest=(
            DailyDigestConfig(time(8), Percentage(Decimal("20.00")))
            if digest
            else None
        ),
        individual_notifications_enabled=individual_notifications,
        retention_preview_days=retention_preview_days,
    )


def test_catalog_composition_assembles_shared_sqlite_stack() -> None:
    config = _catalog_config()

    result = _compose_homeassistant(config, "token", lambda: TIMESTAMP, uuid4)

    assert result.workflow is None
    assert isinstance(result.catalog_workflow, CatalogMonitoringWorkflow)
    assert result.interval == timedelta(seconds=300)
    assert result.discovery_interval_cycles == 48
    assert dict(result.rules[0].parameters) == {
        "percentage": Decimal("20.00"),
        "available_only": True,
    }
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
    assert isinstance(
        synchronizer._notification_reservation_store,
        SqliteNotificationReservationStore,
    )
    assert synchronizer._state_store._database._path == Path(
        "/data/catalog.sqlite3"
    )
    assert synchronizer._http_client._timeout_seconds == 12
    channel = synchronizer._notification_channel
    assert isinstance(channel, HomeAssistantNotificationChannel)
    assert channel._entity_id == "notify.gmail_parkside"
    assert channel._title == "Parkside Catalog"
    assert result.daily_digest_workflow is None
    assert result.catalog_status is not None
    assert isinstance(
        result.catalog_status.publisher,
        HomeAssistantCatalogStatusPublisher,
    )
    assert result.catalog_status.statistics_reader is workflow._catalog_store
    assert result.catalog_status.snapshot_reader is synchronizer._state_store
    assert result.catalog_status.provider_id == LidlParksideCatalog.id
    assert result.catalog_status.minimum_discount == Percentage(Decimal("20.00"))
    assert result.storage_status is not None
    assert isinstance(
        result.storage_status.publisher,
        HomeAssistantStorageStatusPublisher,
    )
    assert result.storage_status.statistics_reader is synchronizer._state_store
    assert result.maintenance_status is None


def test_catalog_composition_assembles_optional_retention_preview() -> None:
    result = _compose_homeassistant(
        _catalog_config(retention_preview_days=90),
        "token",
        lambda: TIMESTAMP,
        uuid4,
    )

    context = result.maintenance_status
    assert isinstance(context, _MaintenanceStatusComposition)
    assert isinstance(
        context.publisher,
        HomeAssistantMaintenanceStatusPublisher,
    )
    assert isinstance(context.retention_manager, SqliteObservationRetentionManager)
    assert context.retention_manager._database._path == Path(
        "/data/catalog.sqlite3"
    )
    assert context.retention_days == 90


@pytest.mark.parametrize(
    ("days", "exception_type"),
    [(True, TypeError), ("90", TypeError), (0, ValueError)],
)
def test_maintenance_composition_validates_retention_days(
    days: object,
    exception_type: type[Exception],
) -> None:
    with pytest.raises(exception_type, match="retention_days"):
        _MaintenanceStatusComposition(
            publisher=cast(object, object()),
            retention_manager=cast(object, object()),
            retention_days=cast(int, days),
        )


def test_maintenance_composition_validates_apply_availability() -> None:
    with pytest.raises(TypeError, match="apply_available"):
        _MaintenanceStatusComposition(
            publisher=cast(object, object()),
            retention_manager=cast(object, object()),
            retention_days=90,
            apply_available=cast(bool, "yes"),
        )


def test_explicit_composition_rejects_maintenance_status() -> None:
    maintenance = _MaintenanceStatusComposition(
        publisher=cast(object, object()),
        retention_manager=cast(object, object()),
        retention_days=90,
    )

    with pytest.raises(ValueError, match="maintenance status requires catalog"):
        _HomeAssistantComposition(
            workflow=cast(object, object()),
            status_publisher=cast(object, object()),
            rules=(),
            interval=timedelta(minutes=5),
            maintenance_status=maintenance,
        )


def test_catalog_composition_assembles_optional_daily_digest() -> None:
    result = _compose_homeassistant(
        _catalog_config(digest=True),
        "token",
        lambda: TIMESTAMP,
        uuid4,
    )

    workflow = result.daily_digest_workflow
    assert isinstance(workflow, DailyDigestWorkflow)
    assert isinstance(workflow._snapshot_reader, SqliteStateStore)
    assert isinstance(
        workflow._reservation_store,
        SqliteDailyDigestReservationStore,
    )
    assert isinstance(
        workflow._digest_channel,
        HomeAssistantDailyDiscountDigestChannel,
    )
    assert workflow._digest_channel._entity_id == "notify.gmail_parkside"
    assert workflow._digest_channel._title == "Parkside Catalog Daily Digest"
    assert str(workflow._timezone) == "Europe/Prague"
    assert isinstance(
        workflow._promotion_source,
        LidlMarketingPromotionSource,
    )
    assert (
        workflow._promotion_source._http_client
        is result.catalog_workflow._batch_synchronizer._http_client
    )


def test_catalog_composition_can_disable_only_individual_notifications() -> None:
    result = _compose_homeassistant(
        _catalog_config(digest=True, individual_notifications=False),
        "token",
        lambda: TIMESTAMP,
        uuid4,
    )

    assert result.rules == ()
    assert isinstance(result.daily_digest_workflow, DailyDigestWorkflow)
    assert result.catalog_workflow is not None
    assert result.catalog_status is not None
    assert result.storage_status is not None


def test_catalog_composition_preserves_disabled_percentage_status() -> None:
    config = HomeAssistantConfig(
        application=None,
        catalog=CatalogMonitoringConfig(
            Path("/data/catalog.sqlite3"),
            timedelta(minutes=5),
            price_drop_percentage=None,
            price_drop_amount=Decimal("500"),
        ),
        notify_entity="notify.gmail_parkside",
    )

    result = _compose_homeassistant(config, "token", lambda: TIMESTAMP, uuid4)

    assert result.catalog_status is not None
    assert result.catalog_status.minimum_discount is None


def test_batch_synchronizer_reuses_standard_workflow() -> None:
    registry = EvaluatorRegistry()
    registry.register(BackInStockEvaluator())
    store = InMemoryStateStore()
    reservations = cast(object, type(
        "Reservations",
        (),
        {
            "reserve": lambda self, reservation, timestamp: True,
            "release": lambda self, reservation: None,
        },
    )())
    history = cast(
        object,
        type("History", (), {"history": lambda self, product_id: ()})(),
    )
    synchronizer = _LidlCatalogBatchSynchronizer(
        cast(object, _TextClient()),
        lambda: TIMESTAMP,
        store,
        RuleEngine(registry),
        NotificationEngine(),
        cast(object, _Channel()),
        lambda: UUID("90000000-0000-4000-8000-000000000001"),
        history,
        PriceReferencePolicy(),
        reservations,
        PriceDropReservationPolicy(),
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

    with pytest.raises(ValueError, match="daily digest"):
        _HomeAssistantComposition(
            workflow=cast(object, object()),
            catalog_workflow=None,
            status_publisher=explicit.status_publisher,
            rules=explicit.rules,
            interval=explicit.interval,
            daily_digest_workflow=cast(DailyDigestWorkflow, object()),
        )

    with pytest.raises(ValueError, match="catalog status"):
        _HomeAssistantComposition(
            workflow=cast(object, object()),
            catalog_workflow=None,
            status_publisher=explicit.status_publisher,
            rules=explicit.rules,
            interval=explicit.interval,
            catalog_status=explicit.catalog_status,
        )

    with pytest.raises(ValueError, match="storage status"):
        _HomeAssistantComposition(
            workflow=cast(object, object()),
            catalog_workflow=None,
            status_publisher=explicit.status_publisher,
            rules=explicit.rules,
            interval=explicit.interval,
            storage_status=cast(_StorageStatusComposition, object()),
        )


def test_composition_defends_against_missing_mode_after_validation() -> None:
    config = _catalog_config()
    object.__setattr__(config, "catalog", None)

    with pytest.raises(ValueError, match="configuration"):
        _compose_homeassistant(config, "token", lambda: TIMESTAMP, uuid4)
