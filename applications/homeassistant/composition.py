"""Concrete Home Assistant workflow composition."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from applications.catalog_monitoring import (
    CatalogMonitoringWorkflow,
    CatalogMonitoringConfig,
)
from applications.daily_digest import DailyDigestConfig, DailyDigestWorkflow
from applications.homeassistant.digest import compose_daily_digest
from applications.homeassistant.configuration import HomeAssistantConfig
from applications.configuration import ApplicationConfig
from applications.synchronization import SynchronizationResult, SynchronizationWorkflow
from applications.version import VERSION
from core.catalog import CatalogStatisticsReader, ProductReference
from core.domain import Percentage, ProviderId, Rule, RuleType
from core.notifications import (
    NotificationChannel,
    NotificationEngine,
    NotificationReservationStore,
    PriceDropReservationPolicy,
)
from core.rules import EvaluatorRegistry, PriceReferencePolicy, RuleEngine
from core.rules.evaluators import BackInStockEvaluator, PriceDropEvaluator
from core.state import (
    LatestSnapshotReader,
    ObservationHistory,
    ObservationRetentionManager,
    ObservationStatisticsReader,
    StateStore,
)
from infrastructure.homeassistant import (
    HomeAssistantCatalogStatusPublisher,
    HomeAssistantMaintenanceStatusPublisher,
    HomeAssistantStatusPublisher,
    HomeAssistantStorageStatusPublisher,
    UrllibHomeAssistantClient,
)
from infrastructure.http import (
    TextHttpClient,
    UrllibBinaryHttpClient,
    UrllibTextHttpClient,
)
from infrastructure.notifications.homeassistant import HomeAssistantNotificationChannel
from infrastructure.persistence.json import JsonStateStore
from infrastructure.persistence.sqlite import (
    SqliteCatalogStore,
    SqliteNotificationReservationStore,
    SqliteObservationRetentionManager,
    SqliteStateStore,
)
from infrastructure.providers.lidl import LidlParksideCatalog, LidlParksideProvider

_SUPERVISOR_CORE_API = "http://supervisor/core/api"
_PRICE_DROP_RULE_ID = UUID("70000000-0000-4000-8000-000000000001")
_BACK_IN_STOCK_RULE_ID = UUID("70000000-0000-4000-8000-000000000002")


@dataclass(frozen=True, slots=True)
class _HomeAssistantComposition:
    """Hold one explicit or catalog monitoring composition."""

    workflow: SynchronizationWorkflow | None
    status_publisher: HomeAssistantStatusPublisher
    rules: tuple[Rule, ...]
    interval: timedelta
    catalog_workflow: CatalogMonitoringWorkflow | None = None
    discovery_interval_cycles: int = 1
    daily_digest_workflow: DailyDigestWorkflow | None = None
    catalog_status: "_CatalogStatusComposition | None" = None
    storage_status: "_StorageStatusComposition | None" = None
    maintenance_status: "_MaintenanceStatusComposition | None" = None

    def __post_init__(self) -> None:
        if (self.workflow is None) == (self.catalog_workflow is None):
            raise ValueError("composition must contain exactly one workflow")
        if self.daily_digest_workflow is not None and self.catalog_workflow is None:
            raise ValueError("daily digest requires catalog workflow")
        if (self.catalog_status is None) != (self.catalog_workflow is None):
            raise ValueError("catalog status requires catalog workflow")
        if (self.storage_status is None) != (self.catalog_workflow is None):
            raise ValueError("storage status requires catalog workflow")
        if self.maintenance_status is not None and self.catalog_workflow is None:
            raise ValueError("maintenance status requires catalog workflow")


@dataclass(frozen=True, slots=True)
class _CatalogStatusComposition:
    """Hold collaborators for aggregate catalog status publication."""

    publisher: HomeAssistantCatalogStatusPublisher
    statistics_reader: CatalogStatisticsReader
    snapshot_reader: LatestSnapshotReader
    provider_id: ProviderId
    minimum_discount: Percentage | None


@dataclass(frozen=True, slots=True)
class _StorageStatusComposition:
    """Hold collaborators for observation storage-health publication."""

    publisher: HomeAssistantStorageStatusPublisher
    statistics_reader: ObservationStatisticsReader


@dataclass(frozen=True, slots=True)
class _MaintenanceStatusComposition:
    """Hold collaborators for observation-retention status and commands."""

    publisher: HomeAssistantMaintenanceStatusPublisher
    retention_manager: ObservationRetentionManager
    retention_days: int
    apply_available: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.retention_days, bool) or not isinstance(
            self.retention_days,
            int,
        ):
            raise TypeError("retention_days must be an int")
        if self.retention_days <= 0:
            raise ValueError("retention_days must be positive")
        if not isinstance(self.apply_available, bool):
            raise TypeError("apply_available must be a bool")


class _LidlCatalogBatchSynchronizer:
    """Adapt selected Lidl references to the existing synchronization workflow."""

    def __init__(
        self,
        http_client: TextHttpClient,
        clock: Callable[[], datetime],
        state_store: StateStore,
        rule_engine: RuleEngine,
        notification_engine: NotificationEngine,
        notification_channel: NotificationChannel,
        notification_id_factory: Callable[[], UUID],
        observation_history: ObservationHistory,
        price_reference_policy: PriceReferencePolicy,
        notification_reservation_store: NotificationReservationStore,
        price_drop_reservation_policy: PriceDropReservationPolicy,
    ) -> None:
        self._http_client = http_client
        self._clock = clock
        self._state_store = state_store
        self._rule_engine = rule_engine
        self._notification_engine = notification_engine
        self._notification_channel = notification_channel
        self._notification_id_factory = notification_id_factory
        self._observation_history = observation_history
        self._price_reference_policy = price_reference_policy
        self._notification_reservation_store = notification_reservation_store
        self._price_drop_reservation_policy = price_drop_reservation_policy

    def synchronize(
        self,
        references: tuple[ProductReference, ...],
        rules: tuple[Rule, ...],
        timestamp: datetime,
    ) -> SynchronizationResult:
        """Create one standard Lidl provider and synchronize its selected URLs."""
        provider = LidlParksideProvider(
            tuple(reference.url for reference in references),
            self._http_client,
            self._clock,
        )
        workflow = SynchronizationWorkflow(
            providers=(provider,),
            state_store=self._state_store,
            rule_engine=self._rule_engine,
            notification_engine=self._notification_engine,
            notification_channel=self._notification_channel,
            notification_id_factory=self._notification_id_factory,
            observation_history=self._observation_history,
            price_reference_policy=self._price_reference_policy,
            notification_reservation_store=self._notification_reservation_store,
            price_drop_reservation_policy=self._price_drop_reservation_policy,
        )
        return workflow.run(rules, timestamp)


def _compose_homeassistant(
    config: HomeAssistantConfig,
    access_token: str,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
) -> _HomeAssistantComposition:
    """Compose the concrete Supervisor-hosted monitoring stack."""
    _validate_composition_arguments(
        config,
        access_token,
        clock,
        notification_id_factory,
    )
    timeout_seconds = _timeout_seconds(config)
    homeassistant_client = UrllibHomeAssistantClient(
        _SUPERVISOR_CORE_API,
        access_token,
        timeout_seconds=timeout_seconds,
        user_agent=f"PriceWatch/{VERSION}",
    )
    status_publisher = HomeAssistantStatusPublisher(homeassistant_client, VERSION)
    notification_channel = HomeAssistantNotificationChannel(
        homeassistant_client,
        config.notify_entity,
        config.notification_title,
    )
    registry = EvaluatorRegistry()
    registry.register(PriceDropEvaluator())
    registry.register(BackInStockEvaluator())
    rule_engine = RuleEngine(registry)
    notification_engine = NotificationEngine()

    if config.catalog is not None:
        return _compose_catalog(
            config.catalog,
            status_publisher,
            notification_channel,
            rule_engine,
            notification_engine,
            homeassistant_client,
            config.notify_entity,
            config.notification_title,
            config.daily_digest,
            config.individual_notifications_enabled,
            config.retention_preview_days,
            clock,
            notification_id_factory,
        )
    application = cast(ApplicationConfig, config.application)
    provider = LidlParksideProvider(
        application.product_urls,
        UrllibTextHttpClient(
            timeout_seconds=application.timeout_seconds,
            user_agent=f"PriceWatch/{VERSION}",
        ),
        clock,
    )
    rules = _create_rules(
        application.price_drop_percentage,
        application.price_drop_amount,
    )
    workflow = SynchronizationWorkflow(
        providers=(provider,),
        state_store=JsonStateStore(application.state_file),
        rule_engine=rule_engine,
        notification_engine=notification_engine,
        notification_channel=notification_channel,
        notification_id_factory=notification_id_factory,
    )
    interval = application.interval
    if interval is None:
        raise ValueError("application interval is required")
    return _HomeAssistantComposition(
        workflow=workflow,
        status_publisher=status_publisher,
        rules=rules,
        interval=interval,
    )


def _compose_catalog(
    catalog_config: CatalogMonitoringConfig,
    status_publisher: HomeAssistantStatusPublisher,
    notification_channel: NotificationChannel,
    rule_engine: RuleEngine,
    notification_engine: NotificationEngine,
    homeassistant_client: UrllibHomeAssistantClient,
    notify_entity: str,
    notification_title: str,
    daily_digest_config: DailyDigestConfig | None,
    individual_notifications_enabled: bool,
    retention_preview_days: int | None,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
) -> _HomeAssistantComposition:
    text_client = UrllibTextHttpClient(
        timeout_seconds=catalog_config.timeout_seconds,
        user_agent=f"PriceWatch/{VERSION}",
    )
    binary_client = UrllibBinaryHttpClient(
        timeout_seconds=catalog_config.timeout_seconds,
        user_agent=f"PriceWatch/{VERSION}",
    )
    catalog = LidlParksideCatalog(binary_client)
    catalog_store = SqliteCatalogStore(catalog_config.database_file)
    state_store = SqliteStateStore(catalog_config.database_file)
    reservation_store = SqliteNotificationReservationStore(
        catalog_config.database_file
    )
    batch_synchronizer = _LidlCatalogBatchSynchronizer(
        text_client,
        clock,
        state_store,
        rule_engine,
        notification_engine,
        notification_channel,
        notification_id_factory,
        state_store,
        PriceReferencePolicy(),
        reservation_store,
        PriceDropReservationPolicy(),
    )
    catalog_workflow = CatalogMonitoringWorkflow(
        catalog,
        catalog_store,
        catalog_store,
        batch_synchronizer,
        LidlParksideCatalog.id,
        catalog_config.batch_size,
    )
    return _HomeAssistantComposition(
        workflow=None,
        catalog_workflow=catalog_workflow,
        status_publisher=status_publisher,
        rules=(
            _create_rules(
                catalog_config.price_drop_percentage,
                catalog_config.price_drop_amount,
                available_only=True,
            )
            if individual_notifications_enabled
            else ()
        ),
        interval=catalog_config.interval,
        discovery_interval_cycles=catalog_config.discovery_interval_cycles,
        daily_digest_workflow=compose_daily_digest(
            daily_digest_config,
            state_store,
            catalog_config.database_file,
            homeassistant_client,
            notify_entity,
            notification_title,
        ),
        catalog_status=_CatalogStatusComposition(
            publisher=HomeAssistantCatalogStatusPublisher(
                homeassistant_client,
                VERSION,
            ),
            statistics_reader=catalog_store,
            snapshot_reader=state_store,
            provider_id=LidlParksideCatalog.id,
            minimum_discount=(
                None
                if catalog_config.price_drop_percentage is None
                else Percentage(catalog_config.price_drop_percentage)
            ),
        ),
        storage_status=_StorageStatusComposition(
            publisher=HomeAssistantStorageStatusPublisher(
                homeassistant_client,
                VERSION,
            ),
            statistics_reader=state_store,
        ),
        maintenance_status=(
            None
            if retention_preview_days is None
            else _MaintenanceStatusComposition(
                publisher=HomeAssistantMaintenanceStatusPublisher(
                    homeassistant_client,
                    VERSION,
                ),
                retention_manager=SqliteObservationRetentionManager(
                    catalog_config.database_file
                ),
                retention_days=retention_preview_days,
            )
        ),
    )


def _timeout_seconds(config: HomeAssistantConfig) -> int:
    if config.catalog is not None:
        return config.catalog.timeout_seconds
    if config.application is None:
        raise ValueError("monitoring configuration is required")
    return config.application.timeout_seconds


def _validate_composition_arguments(
    config: object,
    access_token: object,
    clock: object,
    notification_id_factory: object,
) -> None:
    if not isinstance(config, HomeAssistantConfig):
        raise TypeError("config must be a HomeAssistantConfig")
    if not isinstance(access_token, str):
        raise TypeError("access_token must be a string")
    if not access_token.strip():
        raise ValueError("access_token cannot be blank")
    if not callable(clock):
        raise TypeError("clock must be callable")
    if not callable(notification_id_factory):
        raise TypeError("notification_id_factory must be callable")


def _create_rules(
    percentage: Decimal | None,
    amount: Decimal | None,
    *,
    available_only: bool = False,
) -> tuple[Rule, ...]:
    parameters: dict[str, Decimal | bool] = {}
    if percentage is not None:
        parameters["percentage"] = percentage
    if amount is not None:
        parameters["fixed_amount"] = amount
    if available_only:
        parameters["available_only"] = True
    return (
        Rule(
            id=_PRICE_DROP_RULE_ID,
            name="Price Watch price drop",
            enabled=True,
            rule_type=RuleType.PRICE_DROP,
            parameters=parameters,
        ),
        Rule(
            id=_BACK_IN_STOCK_RULE_ID,
            name="Price Watch back in stock",
            enabled=True,
            rule_type=RuleType.BACK_IN_STOCK,
        ),
    )
