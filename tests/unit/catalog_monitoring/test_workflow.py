"""Tests for bounded catalog monitoring Application orchestration."""

import inspect
from dataclasses import FrozenInstanceError, dataclass, field
from datetime import datetime, timezone
from typing import cast
from uuid import UUID

import pytest

import applications.catalog_monitoring as catalog_api
from applications.catalog_monitoring import (
    CatalogBatchSynchronizer,
    CatalogMonitoringResult,
    CatalogMonitoringWorkflow,
)
from applications.synchronization import SynchronizationResult
from core.catalog import (
    CatalogEntry,
    CatalogError,
    CatalogRefreshStore,
    CatalogStore,
    ProductCatalog,
    ProductReference,
)
from core.domain import ProviderId, Rule, RuleType
from core.provider import ProviderError
from core.state import StateStoreError
from tests.unit.persistence.sqlite_helpers import (
    CATALOG_PROVIDER_ID,
    create_reference,
)

_NOW = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
_RULE = Rule(
    UUID("70000000-0000-4000-8000-000000000001"),
    "price",
    True,
    RuleType.PRICE_DROP,
)


def _synchronization(
    errors: tuple[ProviderError, ...] = (),
) -> SynchronizationResult:
    return SynchronizationResult((), (), (), (), errors)


@dataclass(slots=True)
class _Catalog:
    calls: list[str]
    references: tuple[ProductReference, ...] = ()
    error: CatalogError | None = None

    def discover(self) -> tuple[ProductReference, ...]:
        self.calls.append("discover")
        if self.error is not None:
            raise self.error
        return self.references


@dataclass(slots=True)
class _Store:
    calls: list[str]
    new_references: tuple[ProductReference, ...] = ()
    refresh_references: tuple[ProductReference, ...] = ()
    recorded: list[tuple[tuple[ProductReference, ...], datetime]] = field(
        default_factory=list
    )

    def record_discovery(
        self,
        references: tuple[ProductReference, ...],
        discovered_at: datetime,
    ) -> tuple[ProductReference, ...]:
        self.calls.append("record_discovery")
        return self.new_references

    def list_entries(self, provider_id: ProviderId) -> tuple[CatalogEntry, ...]:
        return ()

    def list_refresh_batch(
        self,
        provider_id: ProviderId,
        limit: int,
    ) -> tuple[ProductReference, ...]:
        self.calls.append(f"list_refresh_batch:{limit}")
        return self.refresh_references

    def record_refresh_attempt(
        self,
        references: tuple[ProductReference, ...],
        attempted_at: datetime,
    ) -> None:
        self.calls.append("record_refresh_attempt")
        self.recorded.append((references, attempted_at))


@dataclass(slots=True)
class _Synchronizer:
    calls: list[str]
    result: SynchronizationResult = field(default_factory=_synchronization)
    error: Exception | None = None

    def synchronize(
        self,
        references: tuple[ProductReference, ...],
        rules: tuple[Rule, ...],
        timestamp: datetime,
    ) -> SynchronizationResult:
        self.calls.append("synchronize")
        if self.error is not None:
            raise self.error
        return self.result


def _workflow(
    catalog: object,
    store: object,
    synchronizer: object,
    batch_size: int = 2,
) -> CatalogMonitoringWorkflow:
    return CatalogMonitoringWorkflow(
        cast(ProductCatalog, catalog),
        cast(CatalogStore, store),
        cast(CatalogRefreshStore, store),
        cast(CatalogBatchSynchronizer, synchronizer),
        CATALOG_PROVIDER_ID,
        batch_size,
    )


def test_public_api_is_explicit_documented_and_typed() -> None:
    assert catalog_api.__all__ == [
        "CatalogBatchSynchronizer",
        "CatalogMonitoringConfig",
        "CatalogMonitoringResult",
        "CatalogMonitoringWorkflow",
    ]
    assert inspect.getdoc(CatalogBatchSynchronizer)
    assert inspect.getdoc(CatalogMonitoringResult)
    assert inspect.getdoc(CatalogMonitoringWorkflow)
    assert inspect.signature(CatalogMonitoringWorkflow.run).return_annotation is (
        CatalogMonitoringResult
    )


def test_protocols_are_structural() -> None:
    calls: list[str] = []
    catalog: ProductCatalog = _Catalog(calls)
    store: CatalogStore = _Store(calls)
    refresh_store: CatalogRefreshStore = _Store(calls)
    synchronizer: CatalogBatchSynchronizer = _Synchronizer(calls)

    assert catalog is not None
    assert store is not None
    assert refresh_store is not None
    assert synchronizer is not None


def test_complete_cycle_preserves_documented_order_and_result() -> None:
    calls: list[str] = []
    references = (create_reference("p1"), create_reference("p2"))
    catalog = _Catalog(calls, references)
    store = _Store(calls, (references[1],), references)
    synchronizer = _Synchronizer(calls)

    result = _workflow(catalog, store, synchronizer).run((_RULE,), _NOW)

    assert calls == [
        "discover",
        "record_discovery",
        "list_refresh_batch:2",
        "synchronize",
        "record_refresh_attempt",
    ]
    assert result == CatalogMonitoringResult(
        references,
        (references[1],),
        references,
        synchronizer.result,
        None,
    )
    assert store.recorded == [(references, _NOW)]


def test_discovery_can_be_skipped_without_touching_catalog() -> None:
    calls: list[str] = []
    reference = create_reference("p1")
    store = _Store(calls, refresh_references=(reference,))

    result = _workflow(_Catalog(calls), store, _Synchronizer(calls)).run(
        (_RULE,),
        _NOW,
        False,
    )

    assert calls == [
        "list_refresh_batch:2",
        "synchronize",
        "record_refresh_attempt",
    ]
    assert result.discovered_references == ()
    assert result.new_references == ()


def test_discovery_error_is_retained_while_known_batch_runs() -> None:
    calls: list[str] = []
    error = CatalogError("sitemap unavailable")
    reference = create_reference("p1")
    store = _Store(calls, refresh_references=(reference,))

    result = _workflow(
        _Catalog(calls, error=error),
        store,
        _Synchronizer(calls),
    ).run((_RULE,), _NOW)

    assert result.catalog_error is error
    assert result.synchronization == _synchronization()
    assert "record_discovery" not in calls


def test_empty_catalog_does_not_invoke_synchronizer_or_record_attempt() -> None:
    calls: list[str] = []

    result = _workflow(_Catalog(calls), _Store(calls), _Synchronizer(calls)).run(
        (_RULE,),
        _NOW,
    )

    assert result.synchronization is None
    assert calls == ["discover", "record_discovery", "list_refresh_batch:2"]


def test_provider_error_result_still_records_attempt() -> None:
    calls: list[str] = []
    reference = create_reference("p1")
    store = _Store(calls, refresh_references=(reference,))
    result = _synchronization((ProviderError("page failed"),))

    cycle = _workflow(_Catalog(calls), store, _Synchronizer(calls, result)).run(
        (_RULE,),
        _NOW,
        False,
    )

    assert cycle.synchronization is result
    assert store.recorded == [((reference,), _NOW)]


def test_propagated_synchronization_failure_does_not_record_attempt() -> None:
    calls: list[str] = []
    failure = StateStoreError("state failed")
    store = _Store(calls, refresh_references=(create_reference("p1"),))

    with pytest.raises(StateStoreError) as captured:
        _workflow(
            _Catalog(calls),
            store,
            _Synchronizer(calls, error=failure),
        ).run((_RULE,), _NOW, False)

    assert captured.value is failure
    assert store.recorded == []


@pytest.mark.parametrize(
    ("field", "value", "exception_type", "message"),
    [
        ("catalog", object(), TypeError, "catalog"),
        ("catalog_store", object(), TypeError, "catalog_store"),
        ("refresh_store", object(), TypeError, "refresh_store"),
        ("synchronizer", object(), TypeError, "batch_synchronizer"),
        ("provider_id", object(), TypeError, "provider_id"),
        ("batch_size", True, TypeError, "batch_size"),
        ("batch_size", 0, ValueError, "batch_size"),
    ],
)
def test_constructor_rejects_invalid_dependencies(
    field: str,
    value: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    calls: list[str] = []
    values: dict[str, object] = {
        "catalog": _Catalog(calls),
        "catalog_store": _Store(calls),
        "refresh_store": _Store(calls),
        "synchronizer": _Synchronizer(calls),
        "provider_id": CATALOG_PROVIDER_ID,
        "batch_size": 2,
    }
    values[field] = value

    with pytest.raises(exception_type, match=message):
        CatalogMonitoringWorkflow(
            cast(ProductCatalog, values["catalog"]),
            cast(CatalogStore, values["catalog_store"]),
            cast(CatalogRefreshStore, values["refresh_store"]),
            cast(CatalogBatchSynchronizer, values["synchronizer"]),
            cast(ProviderId, values["provider_id"]),
            cast(int, values["batch_size"]),
        )


@pytest.mark.parametrize(
    ("rules", "timestamp", "discover", "exception_type", "message"),
    [
        ([], _NOW, True, TypeError, "rules"),
        ((object(),), _NOW, True, TypeError, "rules"),
        ((_RULE,), "now", True, TypeError, "timestamp"),
        ((_RULE,), datetime(2026, 8, 4, 10, 0), True, ValueError, "timestamp"),
        ((_RULE,), _NOW, 1, TypeError, "discover"),
    ],
)
def test_run_rejects_invalid_arguments_before_dependency_calls(
    rules: object,
    timestamp: object,
    discover: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    calls: list[str] = []
    workflow = _workflow(_Catalog(calls), _Store(calls), _Synchronizer(calls))

    with pytest.raises(exception_type, match=message):
        workflow.run(
            cast(tuple[Rule, ...], rules),
            cast(datetime, timestamp),
            cast(bool, discover),
        )

    assert calls == []


@pytest.mark.parametrize(
    "field",
    [
        "discovered_references",
        "new_references",
        "refresh_references",
        "synchronization",
        "catalog_error",
    ],
)
def test_result_rejects_invalid_member_types(field: str) -> None:
    values: dict[str, object] = {
        "discovered_references": (),
        "new_references": (),
        "refresh_references": (),
        "synchronization": None,
        "catalog_error": None,
    }
    values[field] = object()

    with pytest.raises(TypeError, match=field):
        CatalogMonitoringResult(**values)  # type: ignore[arg-type]


def test_result_is_frozen_and_slotted() -> None:
    result = CatalogMonitoringResult((), (), (), None, None)

    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.catalog_error = CatalogError("changed")  # type: ignore[misc]
@pytest.mark.parametrize("source", ["catalog", "store", "refresh"])
def test_workflow_rejects_invalid_reference_results(source: str) -> None:
    calls: list[str] = []
    catalog = _Catalog(calls, cast(tuple[ProductReference, ...], (object(),)))
    store = _Store(
        calls,
        new_references=cast(tuple[ProductReference, ...], (object(),)),
        refresh_references=cast(tuple[ProductReference, ...], (object(),)),
    )
    if source == "catalog":
        store.new_references = ()
        store.refresh_references = ()
    elif source == "store":
        catalog.references = ()
        store.refresh_references = ()
    else:
        catalog.references = ()
        store.new_references = ()

    with pytest.raises(TypeError, match="return a tuple"):
        _workflow(catalog, store, _Synchronizer(calls)).run((_RULE,), _NOW)


def test_workflow_rejects_invalid_synchronizer_result() -> None:
    calls: list[str] = []
    store = _Store(calls, refresh_references=(create_reference("p1"),))
    synchronizer = _Synchronizer(calls)
    object.__setattr__(synchronizer, "result", object())

    with pytest.raises(TypeError, match="SynchronizationResult"):
        _workflow(_Catalog(calls), store, synchronizer).run(
            (_RULE,),
            _NOW,
            False,
        )