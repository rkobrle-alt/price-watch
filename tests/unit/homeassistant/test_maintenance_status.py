"""Tests for Home Assistant observation-retention preview publication."""

from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import cast

import pytest

from core.state import ObservationRetentionPlan
from infrastructure.homeassistant import (
    HomeAssistantError,
    HomeAssistantMaintenanceStatusPublisher,
    MaintenanceStatus,
)
from tests.unit.homeassistant.test_status import (
    FailingStateClient,
    RecordingStateClient,
)
from tests.unit.homeassistant_app.helpers import TIMESTAMP


def _plan() -> ObservationRetentionPlan:
    return ObservationRetentionPlan(TIMESTAMP, 100, 60, 40, 10)


@pytest.mark.parametrize("apply_available", [False, True])
def test_publisher_emits_exact_read_only_preview(apply_available: bool) -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantMaintenanceStatusPublisher(client, "0.25.0")

    publisher.publish(
        MaintenanceStatus(TIMESTAMP, 90, _plan(), apply_available)
    )

    assert client.calls == [
        (
            "sensor.price_watch_maintenance",
            "60",
            {
                "friendly_name": "Price Watch Maintenance",
                "icon": "mdi:database-eye-outline",
                "last_checked": TIMESTAMP.isoformat(),
                "retention_days": 90,
                "cutoff": TIMESTAMP.isoformat(),
                "observation_count": 100,
                "removable_observation_count": 60,
                "retained_observation_count": 40,
                "protected_observation_count": 10,
                "apply_available": apply_available,
                "version": "0.25.0",
            },
        )
    ]


@pytest.mark.parametrize(
    ("arguments", "exception_type", "message"),
    [
        ((object(), "0.25.0"), TypeError, "client"),
        ((RecordingStateClient(), 1), TypeError, "version"),
        ((RecordingStateClient(), " "), ValueError, "version"),
        ((RecordingStateClient(), "0.25.0", 1), TypeError, "entity_id"),
        (
            (RecordingStateClient(), "0.25.0", "button.maintenance"),
            ValueError,
            "entity_id",
        ),
    ],
)
def test_publisher_rejects_invalid_configuration(
    arguments: tuple[object, ...],
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        HomeAssistantMaintenanceStatusPublisher(
            *cast(tuple[object, str, str], arguments)
        )


@pytest.mark.parametrize(
    ("timestamp", "days", "plan", "exception_type", "message"),
    [
        ("now", 90, _plan(), TypeError, "timestamp"),
        (datetime(2026, 8, 1), 90, _plan(), ValueError, "timezone-aware"),
        (TIMESTAMP, True, _plan(), TypeError, "retention_days"),
        (TIMESTAMP, "90", _plan(), TypeError, "retention_days"),
        (TIMESTAMP, 0, _plan(), ValueError, "positive"),
        (TIMESTAMP, 90, object(), TypeError, "plan"),
        (TIMESTAMP, 90, _plan(), TypeError, "apply_available"),
    ],
)
def test_status_rejects_invalid_values(
    timestamp: object,
    days: object,
    plan: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        MaintenanceStatus(
            cast(datetime, timestamp),
            cast(int, days),
            cast(ObservationRetentionPlan, plan),
            cast(bool, "yes") if message == "apply_available" else False,
        )


def test_status_is_immutable_and_publisher_validates_before_side_effect() -> None:
    status = MaintenanceStatus(TIMESTAMP, 90, _plan())
    client = RecordingStateClient()
    publisher = HomeAssistantMaintenanceStatusPublisher(client, "0.25.0")

    with pytest.raises(FrozenInstanceError):
        status.retention_days = 30  # type: ignore[misc]
    with pytest.raises(TypeError, match="status"):
        publisher.publish(cast(MaintenanceStatus, object()))

    assert client.calls == []


def test_publisher_propagates_home_assistant_failure() -> None:
    failure = HomeAssistantError("state failed")
    publisher = HomeAssistantMaintenanceStatusPublisher(
        FailingStateClient(failure),
        "0.25.0",
    )

    with pytest.raises(HomeAssistantError) as captured:
        publisher.publish(MaintenanceStatus(TIMESTAMP, 90, _plan()))

    assert captured.value is failure
