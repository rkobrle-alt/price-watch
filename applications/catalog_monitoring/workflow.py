"""Bounded Application orchestration for catalog discovery and refresh."""

from datetime import datetime
from typing import cast

from applications.catalog_monitoring.batch import CatalogBatchSynchronizer
from applications.catalog_monitoring.result import CatalogMonitoringResult
from applications.synchronization import SynchronizationResult
from core.catalog import (
    CatalogError,
    CatalogRefreshStore,
    CatalogStore,
    ProductCatalog,
    ProductReference,
)
from core.domain import ProviderId, Rule


class CatalogMonitoringWorkflow:
    """Coordinate discovery and one bounded serial synchronization batch."""

    def __init__(
        self,
        catalog: ProductCatalog,
        catalog_store: CatalogStore,
        refresh_store: CatalogRefreshStore,
        batch_synchronizer: CatalogBatchSynchronizer,
        provider_id: ProviderId,
        batch_size: int,
    ) -> None:
        """Validate and retain injected catalog monitoring dependencies."""
        _validate_dependency(catalog, ("discover",), "catalog")
        _validate_dependency(
            catalog_store,
            ("record_discovery", "list_entries"),
            "catalog_store",
        )
        _validate_dependency(
            refresh_store,
            ("list_refresh_batch", "record_refresh_attempt"),
            "refresh_store",
        )
        _validate_dependency(
            batch_synchronizer,
            ("synchronize",),
            "batch_synchronizer",
        )
        if not isinstance(provider_id, ProviderId):
            raise TypeError("provider_id must be a ProviderId")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size must be an int")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        self._catalog = cast(ProductCatalog, catalog)
        self._catalog_store = cast(CatalogStore, catalog_store)
        self._refresh_store = cast(CatalogRefreshStore, refresh_store)
        self._batch_synchronizer = cast(
            CatalogBatchSynchronizer,
            batch_synchronizer,
        )
        self._provider_id = provider_id
        self._batch_size = batch_size

    def run(
        self,
        rules: tuple[Rule, ...],
        timestamp: datetime,
        discover: bool = True,
    ) -> CatalogMonitoringResult:
        """Run optional discovery followed by one bounded refresh batch."""
        _validate_run_arguments(rules, timestamp, discover)
        discovered_references: tuple[ProductReference, ...] = ()
        new_references: tuple[ProductReference, ...] = ()
        catalog_error: CatalogError | None = None

        if discover:
            try:
                discovered_references = self._catalog.discover()
            except CatalogError as error:
                catalog_error = error
            else:
                _validate_reference_result(
                    discovered_references,
                    "catalog discover",
                )
                new_references = self._catalog_store.record_discovery(
                    discovered_references,
                    timestamp,
                )
                _validate_reference_result(
                    new_references,
                    "catalog store",
                )

        refresh_references = self._refresh_store.list_refresh_batch(
            self._provider_id,
            self._batch_size,
        )
        _validate_reference_result(refresh_references, "refresh store")
        synchronization: SynchronizationResult | None = None
        if refresh_references:
            synchronization = self._batch_synchronizer.synchronize(
                refresh_references,
                rules,
                timestamp,
            )
            if not isinstance(synchronization, SynchronizationResult):
                raise TypeError(
                    "batch synchronizer must return a SynchronizationResult"
                )
            self._refresh_store.record_refresh_attempt(
                refresh_references,
                timestamp,
            )

        return CatalogMonitoringResult(
            discovered_references=discovered_references,
            new_references=new_references,
            refresh_references=refresh_references,
            synchronization=synchronization,
            catalog_error=catalog_error,
        )


def _validate_dependency(
    dependency: object,
    methods: tuple[str, ...],
    name: str,
) -> None:
    for method in methods:
        if not callable(getattr(dependency, method, None)):
            raise TypeError(f"{name} must expose a callable {method} method")


def _validate_run_arguments(
    rules: object,
    timestamp: object,
    discover: object,
) -> None:
    if not isinstance(rules, tuple) or not all(
        isinstance(rule, Rule) for rule in rules
    ):
        raise TypeError("rules must be a tuple of Rule instances")
    if not isinstance(timestamp, datetime):
        raise TypeError("timestamp must be a datetime")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    if not isinstance(discover, bool):
        raise TypeError("discover must be a bool")


def _validate_reference_result(value: object, source: str) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(reference, ProductReference) for reference in value
    ):
        raise TypeError(
            f"{source} must return a tuple of ProductReference values"
        )
