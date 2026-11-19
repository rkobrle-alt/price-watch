"""Retention preview must not delay or run in every monitoring cycle."""

from dataclasses import replace
from datetime import timedelta
from io import StringIO

from applications.homeassistant.composition import _MaintenanceStatusComposition
from applications.homeassistant.cycle import publish_maintenance_status, execute_catalog_cycle
from infrastructure.homeassistant import HomeAssistantError
from tests.unit.homeassistant_app.helpers import TIMESTAMP
from tests.unit.homeassistant_app.test_catalog_main import _RetentionManager, _MaintenanceStatusPublisher
from core.state import ObservationRetentionPlan


def test_preview_interval_manual_force_and_failed_publish() -> None:
    from types import SimpleNamespace
    plan = ObservationRetentionPlan(TIMESTAMP - timedelta(days=90), 0, 0, 0, 0)
    manager = _RetentionManager(plan)
    publisher = _MaintenanceStatusPublisher()
    context = _MaintenanceStatusComposition(publisher, manager, 90)
    composition = SimpleNamespace(maintenance_status=context)
    stderr = StringIO()
    assert publish_maintenance_status(composition, TIMESTAMP, stderr, force=False)
    assert publish_maintenance_status(composition, TIMESTAMP + timedelta(hours=23), stderr, force=False)
    assert len(manager.cutoffs) == 1
    assert publish_maintenance_status(composition, TIMESTAMP + timedelta(hours=24), stderr, force=False)
    assert len(manager.cutoffs) == 2
    assert publish_maintenance_status(composition, TIMESTAMP + timedelta(hours=24, minutes=1), stderr)
    assert len(manager.cutoffs) == 3
    publisher.failure = HomeAssistantError("offline")
    assert not publish_maintenance_status(composition, TIMESTAMP + timedelta(hours=49), stderr, force=False)
    publisher.failure = None
    assert publish_maintenance_status(composition, TIMESTAMP + timedelta(hours=49), stderr, force=False)
    assert len(manager.cutoffs) == 5
    # A backwards clock must not suppress scans indefinitely.
    assert publish_maintenance_status(composition, TIMESTAMP, stderr, force=False)


def test_daily_digest_runs_before_preview(monkeypatch) -> None:
    from tests.unit.homeassistant_app.test_catalog_main import _CatalogWorkflow, _composition, _result
    calls = []
    composition = _composition(_CatalogWorkflow([_result()]))
    monkeypatch.setattr("applications.homeassistant.cycle._run_daily_digest", lambda *args: calls.append("digest"))
    monkeypatch.setattr("applications.homeassistant.cycle.publish_maintenance_status", lambda *args, **kwargs: calls.append("preview") or True)
    execute_catalog_cycle(composition, StringIO(), StringIO(), TIMESTAMP, False)
    assert calls == ["digest", "preview"]
