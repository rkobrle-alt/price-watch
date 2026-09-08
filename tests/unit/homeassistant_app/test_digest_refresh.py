"""Bounded serial digest adapter and operational evidence tests."""

from datetime import datetime
from typing import cast
from typing import TextIO

from applications.catalog_monitoring import CatalogBatchSynchronizer, CatalogMonitoringResult
from applications.daily_digest import DailyDigestResult, DailyDigestStatus
from applications.homeassistant.digest_refresh import _LidlDigestRefresher
from applications.homeassistant.cycle import _operational_failure_kind, _digest_summary
from applications.synchronization import SynchronizationResult
from core.catalog import ProductReference
from core.domain import Product, Rule
from core.notifications import DigestProductRefresher
from core.operations import OperationalFailureKind
from core.provider import ProviderError
from tests.unit.notifications.test_daily_digest import _product, _TIMESTAMP, _DATE
from tests.unit.homeassistant_app.helpers import RecordingStream, TIMESTAMP
from tests.unit.homeassistant_app.test_catalog_main import (
    _CatalogWorkflow, _DigestWorkflow, _OperationalWorkflow,
    _composition, _execute_catalog_cycle, _result,
)


class _Batch:
    def __init__(self) -> None:
        self.calls: list[tuple[ProductReference, ...]] = []
        self.error = ProviderError("offline")

    def synchronize(self, references: tuple[ProductReference, ...], rules: tuple[Rule, ...], timestamp: datetime) -> SynchronizationResult:
        assert rules == ()
        assert timestamp == _TIMESTAMP
        self.calls.append(references)
        return SynchronizationResult((), (), (), (), (self.error,))


def test_adapter_bounds_batches_and_retains_errors_without_individual_alerts() -> None:
    batch = _Batch()
    refresher: DigestProductRefresher = _LidlDigestRefresher(cast(CatalogBatchSynchronizer, batch))
    products: tuple[Product, ...] = tuple(_product(i, "Tool", "20") for i in range(1, 54))
    errors = refresher.refresh(products, _TIMESTAMP)
    assert [len(call) for call in batch.calls] == [25, 25, 3]
    assert tuple(r.url for call in batch.calls for r in call) == tuple(p.url for p in products)
    assert errors == (batch.error,) * 3
    assert refresher.refresh((), _TIMESTAMP) == ()
    assert len(batch.calls) == 3


def test_refresh_failure_is_operational_and_visible_in_summary() -> None:
    result = DailyDigestResult(_DATE, DailyDigestStatus.SENT, refresh_errors=(ProviderError("offline"),))
    catalog = CatalogMonitoringResult((), (), (), None, None)
    assert _operational_failure_kind(catalog, (), result) is OperationalFailureKind.PARTIAL_PROVIDER_FAILURE
    assert "digest_refresh_errors=1" in _digest_summary(result)


def test_cycle_reports_refresh_error_to_log_and_operational_workflow() -> None:
    operational = _OperationalWorkflow()
    digest = _DigestWorkflow(DailyDigestResult(
        TIMESTAMP.date(), DailyDigestStatus.SENT,
        refresh_errors=(ProviderError("refresh offline"),),
    ))
    composition = _composition(
        _CatalogWorkflow([_result()]), digest,
        operational_workflow=operational,
    )
    stdout = RecordingStream()
    stderr = RecordingStream()
    _execute_catalog_cycle(
        composition, cast(TextIO, stdout), cast(TextIO, stderr), TIMESTAMP, False,
    )
    assert "digest refresh error: refresh offline" in stderr.text
    assert "digest_refresh_errors=1" in stdout.text
    assert operational.calls[0][0].failure_kind is OperationalFailureKind.PARTIAL_PROVIDER_FAILURE
