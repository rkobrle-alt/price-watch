"""Tests for Home Assistant observation storage publication."""

from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import cast

import pytest

from core.state import ObservationStatistics
from infrastructure.homeassistant import (
    HomeAssistantError,
    HomeAssistantStorageStatusPublisher,
    StorageStatus,
)
from tests.unit.homeassistant.test_status import (
    FailingStateClient,
    RecordingStateClient,
)
from tests.unit.homeassistant_app.helpers import TIMESTAMP


def _statistics() -> ObservationStatistics:
    return ObservationStatistics(2500, 1879, TIMESTAMP, TIMESTAMP, 1048576)


def test_publisher_emits_exact_healthy_storage_state() -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantStorageStatusPublisher(client, "0.23.0")

    publisher.publish(StorageStatus(TIMESTAMP, _statistics()))

    assert client.calls == [
        (
            "sensor.price_watch_storage",
            "ok",
            {
                "friendly_name": "Price Watch Storage",
                "icon": "mdi:database-check-outline",
                "last_checked": TIMESTAMP.isoformat(),
                "observation_count": 2500,
                "observed_product_count": 1879,
                "first_observation_at": TIMESTAMP.isoformat(),
                "last_observation_at": TIMESTAMP.isoformat(),
                "storage_size_bytes": 1048576,
                "version": "0.23.0",
            },
        )
    ]


def test_publisher_emits_exact_warning_without_statistics() -> None:
    client = RecordingStateClient()

    HomeAssistantStorageStatusPublisher(
        client,
        "0.23.0",
        "sensor.custom_storage",
    ).publish(StorageStatus(TIMESTAMP, None))

    assert client.calls[0][0:2] == ("sensor.custom_storage", "warning")
    assert client.calls[0][2] == {
        "friendly_name": "Price Watch Storage",
        "icon": "mdi:database-check-outline",
        "last_checked": TIMESTAMP.isoformat(),
        "observation_count": None,
        "observed_product_count": None,
        "first_observation_at": None,
        "last_observation_at": None,
        "storage_size_bytes": None,
        "version": "0.23.0",
    }


@pytest.mark.parametrize(
    ("arguments", "exception_type", "message"),
    [
        ((object(), "0.23.0"), TypeError, "client"),
        ((RecordingStateClient(), 1), TypeError, "version"),
        ((RecordingStateClient(), " "), ValueError, "version"),
        ((RecordingStateClient(), "0.23.0", 1), TypeError, "entity_id"),
        (
            (RecordingStateClient(), "0.23.0", "binary_sensor.storage"),
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
        HomeAssistantStorageStatusPublisher(
            *cast(tuple[object, str, str], arguments)
        )


@pytest.mark.parametrize(
    ("timestamp", "statistics", "exception_type", "message"),
    [
        ("now", None, TypeError, "timestamp"),
        (datetime(2026, 8, 1), None, ValueError, "timezone-aware"),
        (TIMESTAMP, object(), TypeError, "statistics"),
    ],
)
def test_storage_status_rejects_invalid_values(
    timestamp: object,
    statistics: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        StorageStatus(
            cast(datetime, timestamp),
            cast(ObservationStatistics | None, statistics),
        )


def test_status_is_immutable_and_publisher_validates_before_side_effect() -> None:
    status = StorageStatus(TIMESTAMP, _statistics())
    client = RecordingStateClient()
    publisher = HomeAssistantStorageStatusPublisher(client, "0.23.0")

    with pytest.raises(FrozenInstanceError):
        status.statistics = None  # type: ignore[misc]
    with pytest.raises(TypeError, match="status"):
        publisher.publish(cast(StorageStatus, object()))

    assert client.calls == []


def test_publisher_propagates_home_assistant_failure() -> None:
    failure = HomeAssistantError("state failed")
    publisher = HomeAssistantStorageStatusPublisher(
        FailingStateClient(failure),
        "0.23.0",
    )

    with pytest.raises(HomeAssistantError) as captured:
        publisher.publish(StorageStatus(TIMESTAMP, None))

    assert captured.value is failure
