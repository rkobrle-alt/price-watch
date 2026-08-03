"""Home Assistant cycle execution and status publication."""

from datetime import datetime
from typing import TextIO

from applications.catalog_monitoring import CatalogMonitoringResult
from applications.homeassistant.composition import _HomeAssistantComposition
from applications.synchronization import SynchronizationResult
from core.domain import Product
from infrastructure.homeassistant import HomeAssistantError


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
    status_published = _publish_status(
        composition,
        products,
        timestamp,
        notification_count,
        provider_error_count + catalog_error_count,
        stderr,
    )
    _write(
        stdout,
        "catalog sync complete: "
        f"discovered={len(result.discovered_references)} "
        f"new={len(result.new_references)} "
        f"selected={len(result.refresh_references)} "
        f"products={len(products)} "
        f"evaluations={evaluation_count} "
        f"notifications={notification_count} "
        f"snapshots={snapshot_count} "
        f"provider_errors={provider_error_count} "
        f"catalog_errors={catalog_error_count} "
        f"status_published={str(status_published).lower()}\n",
    )
    return result, status_published


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
