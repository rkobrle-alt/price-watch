"""Tests for Home Assistant catalog-cycle execution and scheduling."""

import importlib
from dataclasses import dataclass, field
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import TextIO, cast
from uuid import UUID, uuid4

import pytest

from applications.catalog_monitoring import CatalogMonitoringResult
from applications.daily_digest import DailyDigestResult, DailyDigestStatus
from applications.homeassistant.composition import _HomeAssistantComposition
from applications.homeassistant.composition import _CatalogStatusComposition
from applications.homeassistant.composition import _StorageStatusComposition
from applications.homeassistant.cycle import publish_storage_warning
from applications.homeassistant.main import (
    _execute_catalog_cycle,
    _execute_cycle,
    run,
)
from applications.synchronization import SynchronizationResult
from core.catalog import CatalogError, CatalogStatistics, CatalogStoreError
from core.domain import Money, Notification, Percentage
from core.notifications import (
    DailyDigestReservationError,
    NotificationReservationError,
)
from core.state import ObservationStatistics, StateSnapshot, StateStoreError
from infrastructure.homeassistant import (
    CatalogStatus,
    HomeAssistantError,
    StorageStatus,
)
from infrastructure.providers.lidl import LidlParksideCatalog
from core.provider import ProviderError
from tests.unit.homeassistant_app.helpers import (
    RecordingDelay,
    RecordingStream,
    TIMESTAMP,
)
from tests.unit.notifications.helpers import create_product

_homeassistant_main = importlib.import_module("applications.homeassistant.main")


@dataclass(slots=True)
class _CatalogWorkflow:
    results: list[CatalogMonitoringResult]
    discoveries: list[bool] = field(default_factory=list)

    def run(
        self,
        rules: tuple,
        timestamp: object,
        discover: bool,
    ) -> CatalogMonitoringResult:
        self.discoveries.append(discover)
        return self.results.pop(0)

_homeassistant_main = importlib.import_module("applications.homeassistant.main")


@dataclass(slots=True)
class _StatusPublisher:
    calls: list[tuple] = field(default_factory=list)

    def publish_cycle(
        self,
        products: tuple,
        timestamp: object,
        notification_count: int,
        provider_error_count: int,
    ) -> None:
        self.calls.append(
            (products, timestamp, notification_count, provider_error_count)
        )


@dataclass(slots=True)
class _CatalogStatusPublisher:
    calls: list[CatalogStatus] = field(default_factory=list)
    failure: HomeAssistantError | None = None

    def publish(self, status: CatalogStatus) -> None:
        if self.failure is not None:
            raise self.failure
        self.calls.append(status)


@dataclass(slots=True)
class _StorageStatusPublisher:
    calls: list[StorageStatus] = field(default_factory=list)
    failure: HomeAssistantError | None = None

    def publish(self, status: StorageStatus) -> None:
        if self.failure is not None:
            raise self.failure
        self.calls.append(status)


@dataclass(slots=True)
class _StatisticsReader:
    statistics: CatalogStatistics = CatalogStatistics(10, TIMESTAMP, TIMESTAMP)

    def catalog_statistics(self, provider_id: object) -> CatalogStatistics:
        assert provider_id == LidlParksideCatalog.id
        return self.statistics


@dataclass(slots=True)
class _SnapshotReader:
    snapshots: tuple[StateSnapshot, ...] = ()

    def latest_snapshots(self) -> tuple[StateSnapshot, ...]:
        return self.snapshots


@dataclass(slots=True)
class _ObservationStatisticsReader:
    statistics: ObservationStatistics = ObservationStatistics(
        20,
        10,
        TIMESTAMP,
        TIMESTAMP,
        4096,
    )

    def observation_statistics(self) -> ObservationStatistics:
        return self.statistics


@dataclass(slots=True)
class _DigestWorkflow:
    result: DailyDigestResult
    timestamps: list[object] = field(default_factory=list)

    def run(self, timestamp: object) -> DailyDigestResult:
        self.timestamps.append(timestamp)
        return self.result


def _result(
    *,
    catalog_error: CatalogError | None = None,
    provider_errors: tuple[ProviderError, ...] = (),
    synchronization: bool = True,
    suppressed_notifications: int = 0,
    notification_count: int = 0,
) -> CatalogMonitoringResult:
    notifications = tuple(
        Notification(
            UUID(int=index + 1),
            create_product().id,
            "test notification",
            TIMESTAMP,
        )
        for index in range(notification_count)
    )
    sync = (
        SynchronizationResult(
            (),
            (),
            notifications,
            (),
            provider_errors,
            suppressed_notifications,
        )
        if synchronization
        else None
    )
    return CatalogMonitoringResult((), (), (), sync, catalog_error)


def _composition(
    workflow: _CatalogWorkflow,
    digest_workflow: _DigestWorkflow | None = None,
    *,
    catalog_publisher: _CatalogStatusPublisher | None = None,
    storage_publisher: _StorageStatusPublisher | None = None,
    snapshots: tuple[StateSnapshot, ...] = (),
    minimum_discount: Percentage | None = Percentage(Decimal("20.00")),
) -> _HomeAssistantComposition:
    aggregate_publisher = catalog_publisher or _CatalogStatusPublisher()
    return _HomeAssistantComposition(
        workflow=None,
        catalog_workflow=cast(object, workflow),
        status_publisher=cast(object, _StatusPublisher()),
        rules=(),
        interval=timedelta(seconds=300),
        discovery_interval_cycles=2,
        daily_digest_workflow=cast(object, digest_workflow),
        catalog_status=_CatalogStatusComposition(
            publisher=cast(object, aggregate_publisher),
            statistics_reader=cast(object, _StatisticsReader()),
            snapshot_reader=cast(object, _SnapshotReader(snapshots)),
            provider_id=LidlParksideCatalog.id,
            minimum_discount=minimum_discount,
        ),
        storage_status=_StorageStatusComposition(
            publisher=cast(
                object,
                storage_publisher or _StorageStatusPublisher(),
            ),
            statistics_reader=cast(object, _ObservationStatisticsReader()),
        ),
    )


def test_catalog_watch_discovers_first_and_at_configured_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _CatalogWorkflow([_result(), _result(), _result()])
    composition = _composition(workflow)
    monkeypatch.setattr(
        _homeassistant_main,
        "parse_homeassistant_options",
        lambda options, data_directory: object(),
    )
    monkeypatch.setattr(
        _homeassistant_main,
        "_compose_homeassistant",
        lambda config, token, clock, factory: composition,
    )
    stdout = RecordingStream()
    stderr = RecordingStream()
    delay = RecordingDelay()

    exit_code = run(
        {},
        "token",
        cast(TextIO, stdout),
        cast(TextIO, stderr),
        lambda: TIMESTAMP,
        uuid4,
        delay,
        max_cycles=3,
    )

    assert exit_code == 0
    assert workflow.discoveries == [True, False, True]
    assert delay.durations == [timedelta(seconds=300), timedelta(seconds=300)]
    assert stdout.text.count("catalog sync complete:") == 3
    assert "catalog_error_cycles=0" in stdout.text
    assert stderr.text == ""


def test_catalog_and_provider_errors_are_reported_and_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = CatalogError("sitemap failed")
    provider_error = ProviderError("page failed")
    workflow = _CatalogWorkflow(
        [_result(catalog_error=error, provider_errors=(provider_error,))]
    )
    composition = _composition(workflow)
    monkeypatch.setattr(
        _homeassistant_main,
        "parse_homeassistant_options",
        lambda options, data_directory: object(),
    )
    monkeypatch.setattr(
        _homeassistant_main,
        "_compose_homeassistant",
        lambda config, token, clock, factory: composition,
    )
    stdout = RecordingStream()
    stderr = RecordingStream()

    exit_code = run(
        {},
        "token",
        cast(TextIO, stdout),
        cast(TextIO, stderr),
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        max_cycles=1,
    )

    assert exit_code == 1
    assert "catalog error: sitemap failed" in stderr.text
    assert "provider error: page failed" in stderr.text
    assert "provider_error_cycles=1" in stdout.text
    assert "catalog_error_cycles=1" in stdout.text
    publisher = cast(_StatusPublisher, composition.status_publisher)
    assert publisher.calls[0][3] == 2


def test_empty_catalog_cycle_publishes_empty_status_and_summary() -> None:
    workflow = _CatalogWorkflow([_result(synchronization=False)])
    composition = _composition(workflow)
    stdout = RecordingStream()
    stderr = RecordingStream()

    result, published = _execute_catalog_cycle(
        composition,
        cast(TextIO, stdout),
        cast(TextIO, stderr),
        TIMESTAMP,
        True,
    )

    assert result.synchronization is None
    assert published is True
    assert "products=0" in stdout.text
    assert "suppressed_notifications=0" in stdout.text
    publisher = cast(_StatusPublisher, composition.status_publisher)
    assert publisher.calls == [((), TIMESTAMP, 0, 0)]


def test_catalog_summary_reports_suppressed_notifications() -> None:
    workflow = _CatalogWorkflow([_result(suppressed_notifications=2)])
    stdout = RecordingStream()

    _execute_catalog_cycle(
        _composition(workflow),
        cast(TextIO, stdout),
        cast(TextIO, RecordingStream()),
        TIMESTAMP,
        False,
    )

    assert "suppressed_notifications=2" in stdout.text


def test_catalog_cycle_publishes_complete_aggregate_status() -> None:
    product = replace(
        create_product(),
        provider_id=LidlParksideCatalog.id,
        original_price=Money(Decimal("200"), create_product().currency),
        discount_percent=Percentage(Decimal("50")),
    )
    other_provider_product = create_product()
    publisher = _CatalogStatusPublisher()
    composition = _composition(
        _CatalogWorkflow(
            [_result(notification_count=1, suppressed_notifications=2)]
        ),
        catalog_publisher=publisher,
        snapshots=(
            StateSnapshot(product, TIMESTAMP),
            StateSnapshot(other_provider_product, TIMESTAMP),
        ),
    )

    _, published = _execute_catalog_cycle(
        composition,
        cast(TextIO, RecordingStream()),
        cast(TextIO, RecordingStream()),
        TIMESTAMP,
        False,
    )

    assert published is True
    assert publisher.calls == [
        CatalogStatus(
            timestamp=TIMESTAMP,
            reference_count=10,
            observed_product_count=1,
            available_product_count=1,
            qualifying_discount_count=1,
            minimum_discount=Percentage(Decimal("20.00")),
            last_discovered_at=TIMESTAMP,
            last_refresh_attempt_at=TIMESTAMP,
            provider_error_count=0,
            catalog_error_count=0,
            notification_count=1,
            suppressed_notification_count=2,
        )
    ]
    storage_context = composition.storage_status
    assert storage_context is not None
    storage_publisher = cast(_StorageStatusPublisher, storage_context.publisher)
    assert storage_publisher.calls == [
        StorageStatus(
            TIMESTAMP,
            ObservationStatistics(20, 10, TIMESTAMP, TIMESTAMP, 4096),
        )
    ]


def test_disabled_percentage_and_catalog_status_failure_are_reported() -> None:
    failure = HomeAssistantError("aggregate failed")
    publisher = _CatalogStatusPublisher(failure=failure)
    composition = _composition(
        _CatalogWorkflow([_result()]),
        catalog_publisher=publisher,
        minimum_discount=None,
    )
    stderr = RecordingStream()

    _, published = _execute_catalog_cycle(
        composition,
        cast(TextIO, RecordingStream()),
        cast(TextIO, stderr),
        TIMESTAMP,
        False,
    )

    assert published is False
    assert stderr.text == "catalog status error: aggregate failed\n"


def test_storage_status_failure_is_non_fatal_and_reported() -> None:
    failure = HomeAssistantError("storage publish failed")
    composition = _composition(
        _CatalogWorkflow([_result()]),
        storage_publisher=_StorageStatusPublisher(failure=failure),
    )
    stderr = RecordingStream()

    _, published = _execute_catalog_cycle(
        composition,
        cast(TextIO, RecordingStream()),
        cast(TextIO, stderr),
        TIMESTAMP,
        False,
    )

    assert published is False
    assert stderr.text == "storage status error: storage publish failed\n"


def test_enabled_digest_runs_after_status_and_is_reported() -> None:
    workflow = _CatalogWorkflow([_result()])
    digest = _DigestWorkflow(
        DailyDigestResult(date(2026, 8, 1), DailyDigestStatus.SENT, 3)
    )
    composition = _composition(workflow, digest)
    stdout = RecordingStream()

    _execute_catalog_cycle(
        composition,
        cast(TextIO, stdout),
        cast(TextIO, RecordingStream()),
        TIMESTAMP,
        False,
    )

    assert digest.timestamps == [TIMESTAMP]
    assert "digest_status=sent digest_products=3" in stdout.text


@pytest.mark.parametrize(
    "failure",
    [
        CatalogStoreError("catalog database failed"),
        StateStoreError("state database failed"),
        NotificationReservationError("reservation database failed"),
        DailyDigestReservationError("digest database failed"),
    ],
)
def test_persistence_failure_publishes_warning_and_returns_operational_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    class _FailingWorkflow:
        def run(self, rules: tuple, timestamp: object, discover: bool) -> None:
            raise failure

    composition = _composition(cast(_CatalogWorkflow, _FailingWorkflow()))
    monkeypatch.setattr(
        _homeassistant_main,
        "parse_homeassistant_options",
        lambda options, data_directory: object(),
    )
    monkeypatch.setattr(
        _homeassistant_main,
        "_compose_homeassistant",
        lambda config, token, clock, factory: composition,
    )
    stderr = RecordingStream()

    exit_code = run(
        {},
        "token",
        cast(TextIO, RecordingStream()),
        cast(TextIO, stderr),
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        max_cycles=1,
    )

    assert exit_code == 1
    assert stderr.text == f"error: {failure}\n"
    storage_context = composition.storage_status
    assert storage_context is not None
    publisher = cast(_StorageStatusPublisher, storage_context.publisher)
    assert publisher.calls == [StorageStatus(TIMESTAMP, None)]


def test_warning_publication_failure_does_not_mask_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = StateStoreError("database failed")

    class _FailingWorkflow:
        def run(self, rules: tuple, timestamp: object, discover: bool) -> None:
            raise failure

    composition = _composition(
        cast(_CatalogWorkflow, _FailingWorkflow()),
        storage_publisher=_StorageStatusPublisher(
            failure=HomeAssistantError("warning failed")
        ),
    )
    monkeypatch.setattr(
        _homeassistant_main,
        "parse_homeassistant_options",
        lambda options, data_directory: object(),
    )
    monkeypatch.setattr(
        _homeassistant_main,
        "_compose_homeassistant",
        lambda config, token, clock, factory: composition,
    )
    stderr = RecordingStream()

    exit_code = run(
        {},
        "token",
        cast(TextIO, RecordingStream()),
        cast(TextIO, stderr),
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        max_cycles=1,
    )

    assert exit_code == 1
    assert stderr.text == (
        "storage status error: warning failed\n"
        "error: database failed\n"
    )

def test_cycle_helpers_reject_wrong_composition_mode() -> None:
    catalog_composition = _composition(_CatalogWorkflow([_result()]))

    with pytest.raises(ValueError, match="explicit synchronization"):
        _execute_cycle(
            catalog_composition,
            cast(TextIO, RecordingStream()),
            cast(TextIO, RecordingStream()),
            TIMESTAMP,
        )

    explicit_composition = _HomeAssistantComposition(
        workflow=cast(object, object()),
        catalog_workflow=None,
        status_publisher=catalog_composition.status_publisher,
        rules=(),
        interval=timedelta(seconds=300),
    )
    with pytest.raises(ValueError, match="catalog monitoring"):
        _execute_catalog_cycle(
            explicit_composition,
            cast(TextIO, RecordingStream()),
            cast(TextIO, RecordingStream()),
            TIMESTAMP,
            True,
        )

    object.__setattr__(catalog_composition, "catalog_status", None)
    with pytest.raises(ValueError, match="catalog status composition"):
        _execute_catalog_cycle(
            catalog_composition,
            cast(TextIO, RecordingStream()),
            cast(TextIO, RecordingStream()),
            TIMESTAMP,
            True,
        )

    object.__setattr__(catalog_composition, "catalog_status", _CatalogStatusComposition(
        publisher=cast(object, _CatalogStatusPublisher()),
        statistics_reader=cast(object, _StatisticsReader()),
        snapshot_reader=cast(object, _SnapshotReader()),
        provider_id=LidlParksideCatalog.id,
        minimum_discount=Percentage(Decimal("20.00")),
    ))
    object.__setattr__(catalog_composition, "storage_status", None)
    workflow = cast(_CatalogWorkflow, catalog_composition.catalog_workflow)
    workflow.results.append(_result())
    with pytest.raises(ValueError, match="storage status composition"):
        _execute_catalog_cycle(
            catalog_composition,
            cast(TextIO, RecordingStream()),
            cast(TextIO, RecordingStream()),
            TIMESTAMP,
            True,
        )

    with pytest.raises(ValueError, match="storage status composition"):
        publish_storage_warning(
            catalog_composition,
            TIMESTAMP,
            cast(TextIO, RecordingStream()),
        )
