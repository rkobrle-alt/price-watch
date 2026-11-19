"""Inventory churn and partial responses must not masquerade as a full outage."""

from datetime import timedelta

from core.operations import OperationalHealthEngine, OperationalCheck, OperationalState, OperationalHealthStatus, OperationalFailureKind
from tests.integration.test_missing_page_lifecycle import NOW


def test_partial_failure_stays_degraded_and_does_not_accelerate_full_outage() -> None:
    engine = OperationalHealthEngine()
    state = OperationalState.initial()
    for minute in range(10):
        state = engine.evaluate(state, OperationalCheck(NOW + timedelta(minutes=minute), OperationalFailureKind.PARTIAL_PROVIDER_FAILURE))
        assert state.status is OperationalHealthStatus.DEGRADED
        assert state.pending_notification is None
    for minute in range(10, 13):
        state = engine.evaluate(state, OperationalCheck(NOW + timedelta(minutes=minute), OperationalFailureKind.PROVIDER_UNAVAILABLE))
        assert state.consecutive_failure_cycles == minute - 9
    assert state.status is OperationalHealthStatus.FAILED
    state = engine.evaluate(state, OperationalCheck(NOW + timedelta(minutes=13), OperationalFailureKind.PARTIAL_PROVIDER_FAILURE))
    assert state.status is OperationalHealthStatus.DEGRADED
    assert state.consecutive_failure_cycles == 1


def test_missing_pages_are_inventory_diagnostics_not_health_failure() -> None:
    from dataclasses import replace
    from applications.homeassistant.cycle import _operational_failure_kind
    from applications.daily_digest import DailyDigestResult, DailyDigestStatus
    from core.provider import ProviderProductNotFoundError, ProviderTransportError
    from core.catalog import ProductReference
    from tests.unit.homeassistant_app.test_catalog_main import _result
    from infrastructure.providers.lidl import LidlParksideProvider
    missing = ProviderProductNotFoundError("404", "https://example.test/missing")
    result = _result(provider_errors=(missing,))
    reference = ProductReference(LidlParksideProvider.id, "missing", missing.url)
    result = replace(result, refresh_references=(reference,))
    assert _operational_failure_kind(result, (), None) is None
    result = replace(result, synchronization=replace(result.synchronization, provider_errors=(missing, ProviderTransportError("timeout"))), refresh_references=(reference, reference))
    assert _operational_failure_kind(result, (), None) is OperationalFailureKind.PROVIDER_UNAVAILABLE
    digest = DailyDigestResult(NOW.date(), DailyDigestStatus.SENT, refresh_errors=(missing,))
    assert _operational_failure_kind(_result(), (), digest) is None
