"""Home Assistant cycle execution and status publication."""

from datetime import datetime, timedelta
from typing import TextIO

from applications.catalog_monitoring import CatalogMonitoringResult
from applications.daily_digest import DailyDigestResult, DailyDigestStatus
from applications.homeassistant.composition import _HomeAssistantComposition
from applications.operational_monitoring import OperationalMonitoringResult
from applications.synchronization import SynchronizationResult
from core.domain import Product
from core.notifications import DailyDiscountDigestEngine
from core.operations import (
    DailyDigestDelivery,
    OperationalCheck,
    OperationalFailureKind,
    OperationalNotificationKind,
)
from core.provider import ProviderDataError, ProviderTransportError
from infrastructure.homeassistant import (
    CatalogStatus,
    HomeAssistantError,
    MaintenanceStatus,
    StorageStatus,
)


def execute_explicit_cycle(
    composition: _HomeAssistantComposition,
    stdout: TextIO,
    stderr: TextIO,
    timestamp: datetime,
) -> tuple[SynchronizationResult, bool]:
    """Execute one explicit-URL cycle and publish its current representation."""
    workflow = composition.workflow
    if workflow is None:
        raise ValueError("explicit synchronization workflow is required")
    result = workflow.run(composition.rules, timestamp)
    for error in result.provider_errors:
        _write(stderr, f"provider error: {error}\n")

    products = _result_products(result)
    status_published = _publish_status(
        composition,
        products,
        timestamp,
        len(result.notifications),
        len(result.provider_errors),
        stderr,
    )
    _write(
        stdout,
        "sync complete: "
        f"products={len(products)} "
        f"evaluations={len(result.evaluations)} "
        f"notifications={len(result.notifications)} "
        f"snapshots={len(result.snapshots)} "
        f"provider_errors={len(result.provider_errors)} "
        f"status_published={str(status_published).lower()}\n",
    )
    return result, status_published


def _publish_catalog_status(
    composition: _HomeAssistantComposition,
    timestamp: datetime,
    provider_error_count: int,
    catalog_error_count: int,
    notification_count: int,
    suppressed_notification_count: int,
    stderr: TextIO,
) -> bool:
    context = composition.catalog_status
    if context is None:
        raise ValueError("catalog status composition is required")
    statistics = context.statistics_reader.catalog_statistics(context.provider_id)
    snapshots = tuple(
        snapshot
        for snapshot in context.snapshot_reader.latest_snapshots()
        if snapshot.product.provider_id == context.provider_id
    )
    available_count = sum(snapshot.product.availability for snapshot in snapshots)
    qualifying_count = 0
    if context.minimum_discount is not None:
        digest = DailyDiscountDigestEngine().generate(
            snapshots,
            context.minimum_discount,
            timestamp.date(),
            timestamp,
        )
        qualifying_count = len(digest.products)
    status = CatalogStatus(
        timestamp=timestamp,
        reference_count=statistics.reference_count,
        observed_product_count=len(snapshots),
        available_product_count=available_count,
        qualifying_discount_count=qualifying_count,
        minimum_discount=context.minimum_discount,
        last_discovered_at=statistics.last_discovered_at,
        last_refresh_attempt_at=statistics.last_refresh_attempt_at,
        provider_error_count=provider_error_count,
        catalog_error_count=catalog_error_count,
        notification_count=notification_count,
        suppressed_notification_count=suppressed_notification_count,
    )
    try:
        context.publisher.publish(status)
    except HomeAssistantError as error:
        _write(stderr, f"catalog status error: {error}\n")
        return False
    return True


def execute_catalog_cycle(
    composition: _HomeAssistantComposition,
    stdout: TextIO,
    stderr: TextIO,
    timestamp: datetime,
    discover: bool,
) -> tuple[CatalogMonitoringResult, bool]:
    """Execute one bounded catalog cycle and publish refreshed products."""
    workflow = composition.catalog_workflow
    if workflow is None:
        raise ValueError("catalog monitoring workflow is required")
    result = workflow.run(composition.rules, timestamp, discover)
    synchronization = result.synchronization
    if result.catalog_error is not None:
        _write(stderr, f"catalog error: {result.catalog_error}\n")
    if synchronization is not None:
        for error in synchronization.provider_errors:
            _write(stderr, f"provider error: {error}\n")
        products = _result_products(synchronization)
        evaluation_count = len(synchronization.evaluations)
        notification_count = len(synchronization.notifications)
        snapshot_count = len(synchronization.snapshots)
        provider_error_count = len(synchronization.provider_errors)
    else:
        products = ()
        evaluation_count = 0
        notification_count = 0
        snapshot_count = 0
        provider_error_count = 0
    catalog_error_count = int(result.catalog_error is not None)
    cycle_status_published = _publish_status(
        composition,
        products,
        timestamp,
        notification_count,
        provider_error_count + catalog_error_count,
        stderr,
    )
    catalog_status_published = _publish_catalog_status(
        composition,
        timestamp,
        provider_error_count,
        catalog_error_count,
        notification_count,
        (
            0
            if synchronization is None
            else synchronization.suppressed_notification_count
        ),
        stderr,
    )
    storage_status_published = _publish_storage_status(
        composition,
        timestamp,
        stderr,
    )
    maintenance_status_published = publish_maintenance_status(
        composition,
        timestamp,
        stderr,
    )
    status_published = (
        cycle_status_published
        and catalog_status_published
        and storage_status_published
        and maintenance_status_published
    )
    digest_result = _run_daily_digest(composition, timestamp)
    operational_result, operational_published = _run_operational_monitoring(
        composition,
        result,
        products,
        digest_result,
        timestamp,
        stderr,
    )
    status_published = status_published and operational_published
    digest_text = _digest_summary(digest_result)
    _write(
        stdout,
        "catalog sync complete: "
        f"discovered={len(result.discovered_references)} "
        f"new={len(result.new_references)} "
        f"selected={len(result.refresh_references)} "
        f"products={len(products)} "
        f"evaluations={evaluation_count} "
        f"notifications={notification_count} "
        "suppressed_notifications="
        f"{0 if synchronization is None else synchronization.suppressed_notification_count} "
        f"snapshots={snapshot_count} "
        f"provider_errors={provider_error_count} "
        f"catalog_errors={catalog_error_count} "
        f"{digest_text}"
        f"health_status={operational_result.state.status.value} "
        "health_failures="
        f"{operational_result.state.consecutive_failure_cycles} "
        "operational_notification="
        f"{_operational_notification_summary(operational_result)} "
        f"status_published={str(status_published).lower()}\n",
    )
    return result, status_published


def publish_storage_warning(
    composition: _HomeAssistantComposition,
    timestamp: datetime,
    stderr: TextIO,
) -> bool:
    """Publish a best-effort warning without reading failed persistence."""
    context = composition.storage_status
    if context is None:
        raise ValueError("storage status composition is required")
    try:
        context.publisher.publish(StorageStatus(timestamp, None))
    except HomeAssistantError as error:
        _write(stderr, f"storage status error: {error}\n")
        return False
    return True


def _publish_storage_status(
    composition: _HomeAssistantComposition,
    timestamp: datetime,
    stderr: TextIO,
) -> bool:
    context = composition.storage_status
    if context is None:
        raise ValueError("storage status composition is required")
    statistics = context.statistics_reader.observation_statistics()
    try:
        context.publisher.publish(StorageStatus(timestamp, statistics))
    except HomeAssistantError as error:
        _write(stderr, f"storage status error: {error}\n")
        return False
    return True


def publish_maintenance_status(
    composition: _HomeAssistantComposition,
    timestamp: datetime,
    stderr: TextIO,
) -> bool:
    """Publish the configured current retention plan without applying it."""
    context = composition.maintenance_status
    if context is None:
        return True
    cutoff = timestamp - timedelta(days=context.retention_days)
    plan = context.retention_manager.plan(cutoff)
    try:
        context.publisher.publish(
            MaintenanceStatus(
                timestamp,
                context.retention_days,
                plan,
                context.apply_available,
            )
        )
    except HomeAssistantError as error:
        _write(stderr, f"maintenance status error: {error}\n")
        return False
    return True


def _run_daily_digest(
    composition: _HomeAssistantComposition,
    timestamp: datetime,
) -> DailyDigestResult | None:
    workflow = composition.daily_digest_workflow
    if workflow is None:
        return None
    return workflow.run(timestamp)


def _run_operational_monitoring(
    composition: _HomeAssistantComposition,
    catalog_result: CatalogMonitoringResult,
    products: tuple[Product, ...],
    digest_result: DailyDigestResult | None,
    timestamp: datetime,
    stderr: TextIO,
) -> tuple[OperationalMonitoringResult, bool]:
    context = composition.operational
    if context is None:
        raise ValueError("operational composition is required")
    failure_kind = _operational_failure_kind(
        catalog_result,
        products,
        digest_result,
    )
    delivery = (
        DailyDigestDelivery(
            digest_result.calendar_date,
            timestamp,
            digest_result.product_count,
            digest_result.promotion_included,
        )
        if digest_result is not None
        and digest_result.status is DailyDigestStatus.SENT
        else None
    )
    result = context.workflow.run(
        OperationalCheck(timestamp, failure_kind),
        delivery,
    )
    notification_ok = result.notification_error is None
    if result.notification_error is not None:
        _write(
            stderr,
            f"operational notification error: {result.notification_error}\n",
        )
    digest_status = (
        "disabled" if digest_result is None else digest_result.status.value
    )
    try:
        context.publisher.publish(result.state, digest_status)
    except HomeAssistantError as error:
        _write(stderr, f"operational status error: {error}\n")
        return result, False
    return result, notification_ok


def _operational_failure_kind(
    result: CatalogMonitoringResult,
    products: tuple[Product, ...],
    digest_result: DailyDigestResult | None,
) -> OperationalFailureKind | None:
    if result.catalog_error is not None:
        return OperationalFailureKind.CATALOG_UNAVAILABLE
    synchronization = result.synchronization
    errors = () if synchronization is None else synchronization.provider_errors
    selected_count = len(result.refresh_references)
    if errors and len(errors) == selected_count and not products:
        if all(isinstance(error, ProviderDataError) for error in errors):
            return OperationalFailureKind.PROVIDER_DATA_INCOMPATIBLE
        if all(isinstance(error, ProviderTransportError) for error in errors):
            return OperationalFailureKind.PROVIDER_UNAVAILABLE
        return OperationalFailureKind.PROVIDER_FAILURE
    if errors:
        return OperationalFailureKind.PARTIAL_PROVIDER_FAILURE
    if (
        digest_result is not None
        and digest_result.status is DailyDigestStatus.PROMOTION_UNAVAILABLE
    ):
        return OperationalFailureKind.PROMOTION_UNAVAILABLE
    return None


def _operational_notification_summary(
    result: OperationalMonitoringResult,
) -> str:
    if result.notification_error is not None:
        return "retry"
    if result.notification_sent is OperationalNotificationKind.FAILURE:
        return "failure"
    if result.notification_sent is OperationalNotificationKind.RECOVERY:
        return "recovery"
    return "none"


def _digest_summary(result: DailyDigestResult | None) -> str:
    if result is None:
        return ""
    summary = (
        f"digest_status={result.status.value} "
        f"digest_products={result.product_count} "
    )
    if result.status is DailyDigestStatus.SENT:
        summary += (
            f"digest_promotion={str(result.promotion_included).lower()} "
        )
    return summary


def _result_products(result: SynchronizationResult) -> tuple[Product, ...]:
    return tuple(
        product
        for fetch_result in result.fetch_results
        for product in fetch_result.products
    )


def _publish_status(
    composition: _HomeAssistantComposition,
    products: tuple[Product, ...],
    timestamp: datetime,
    notification_count: int,
    provider_error_count: int,
    stderr: TextIO,
) -> bool:
    try:
        composition.status_publisher.publish_cycle(
            products,
            timestamp,
            notification_count,
            provider_error_count,
        )
    except HomeAssistantError as error:
        _write(stderr, f"status error: {error}\n")
        return False
    return True


def _write(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()
