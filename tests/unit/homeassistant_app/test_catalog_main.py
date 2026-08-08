"""Tests for Home Assistant catalog-cycle execution and scheduling."""

import importlib
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TextIO, cast
from uuid import uuid4

import pytest

from applications.catalog_monitoring import CatalogMonitoringResult
from applications.homeassistant.composition import _HomeAssistantComposition
from applications.homeassistant.main import (
    _execute_catalog_cycle,
    _execute_cycle,
    run,
)
from applications.synchronization import SynchronizationResult
from core.catalog import CatalogError, CatalogStoreError
from core.provider import ProviderError
from tests.unit.homeassistant_app.helpers import (
    RecordingDelay,
    RecordingStream,
    TIMESTAMP,
)

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


def _result(
    *,
    catalog_error: CatalogError | None = None,
    provider_errors: tuple[ProviderError, ...] = (),
    synchronization: bool = True,
    suppressed_notifications: int = 0,
) -> CatalogMonitoringResult:
    sync = (
        SynchronizationResult(
            (),
            (),
            (),
            (),
            provider_errors,
            suppressed_notifications,
        )
        if synchronization
        else None
    )
    return CatalogMonitoringResult((), (), (), sync, catalog_error)


def _composition(workflow: _CatalogWorkflow) -> _HomeAssistantComposition:
    return _HomeAssistantComposition(
        workflow=None,
        catalog_workflow=cast(object, workflow),
        status_publisher=cast(object, _StatusPublisher()),
        rules=(),
        interval=timedelta(seconds=300),
        discovery_interval_cycles=2,
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


def test_catalog_store_failure_returns_operational_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingWorkflow:
        def run(self, rules: tuple, timestamp: object, discover: bool) -> None:
            raise CatalogStoreError("database failed")

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
    assert stderr.text == "error: database failed\n"

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
