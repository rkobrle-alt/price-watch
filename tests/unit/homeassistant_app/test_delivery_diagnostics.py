"""Delivery uncertainty remains visible independently from product failures."""

from dataclasses import replace
from io import StringIO

import pytest

from applications.daily_digest import DailyDigestResult, DailyDigestStatus as Status
from applications.homeassistant.cycle import _operational_failure_kind, execute_catalog_cycle
from core.notifications import DigestDeliveryPhase as Phase, DigestDeliveryRecord
from core.operations import OperationalFailureKind, OperationalState
from infrastructure.homeassistant import HomeAssistantOperationalStatusPublisher
from infrastructure.persistence.sqlite import SqliteDigestDeliveryStore
from tests.unit.homeassistant.test_status import RecordingStateClient
from tests.unit.homeassistant_app.test_catalog_main import _result, _composition, _CatalogWorkflow, _OperationalWorkflow
from tests.integration.test_reliable_digest_delivery import NOW, build


@pytest.mark.parametrize(("status", "expected"), [
    (Status.DELIVERY_RETRY, OperationalFailureKind.DIGEST_DELIVERY_REJECTED),
    (Status.DELIVERY_UNCERTAIN, OperationalFailureKind.DIGEST_DELIVERY_UNCERTAIN),
])
def test_delivery_failure_kind_is_explicit(status, expected) -> None:
    assert _operational_failure_kind(_result(), (), DailyDigestResult(NOW.date(), status)) is expected


def test_delivery_publisher_separates_ha_acceptance_from_mailbox_delivery() -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantOperationalStatusPublisher(client, "1.4.0")
    record = DigestDeliveryRecord(NOW.date(), Phase.ACCEPTED, NOW, 3, promotion_missing=True)
    publisher.publish(OperationalState.initial(), "already_sent", record)
    entity, phase, attributes = client.calls[0]
    assert entity == "sensor.price_watch_digest_delivery" and phase == "accepted"
    assert attributes["acknowledgement_scope"] == "home_assistant_service"
    assert attributes["promotion_missing"] is True
    with pytest.raises(TypeError, match="delivery_record"):
        publisher.publish(OperationalState.initial(), "already_sent", object())


def test_cycle_recovers_operational_receipt_from_accepted_ledger(tmp_path) -> None:
    store = SqliteDigestDeliveryStore(tmp_path / "db")
    store.claim(NOW.date(), NOW)
    store.transition(NOW.date(), Phase.PREPARING, Phase.SENDING, NOW, product_count=3)
    store.transition(NOW.date(), Phase.SENDING, Phase.ACCEPTED, NOW, product_count=3)
    operational = _OperationalWorkflow()
    composition = _composition(_CatalogWorkflow([_result()]), operational_workflow=operational)
    composition = replace(composition, operational=replace(
        composition.operational, delivery_store=store,
        publisher=HomeAssistantOperationalStatusPublisher(RecordingStateClient(), "1.4.0"),
    ))
    execute_catalog_cycle(composition, StringIO(), StringIO(), NOW, False)
    assert operational.calls[0][1].calendar_date == NOW.date()
    assert operational.calls[0][1].product_count == 3


def test_invalid_store_claim_never_dispatches(tmp_path, monkeypatch) -> None:
    store = SqliteDigestDeliveryStore(tmp_path / "db")
    monkeypatch.setattr(store, "claim", lambda *args: Phase.READY)
    with pytest.raises(ValueError, match="claim"):
        build(tmp_path / "db", store=store).run(NOW)
