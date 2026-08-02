"""Tests for Home Assistant cycle status publication."""

from dataclasses import replace
from datetime import datetime
from typing import cast
from uuid import UUID

import pytest

from core.domain import Product, ProductId
from infrastructure.homeassistant import (
    HomeAssistantError,
    HomeAssistantStateClient,
    HomeAssistantStatusPublisher,
)
from tests.unit.homeassistant_app.helpers import TIMESTAMP
from tests.unit.notifications.helpers import create_product


class RecordingStateClient:
    """Capture state publications in order."""

    def __init__(self) -> None:
        """Initialize empty call storage."""
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def set_state(
        self,
        entity_id: str,
        state: str,
        attributes: dict[str, object],
    ) -> None:
        """Record one state publication."""
        self.calls.append((entity_id, state, dict(attributes)))


class FailingStateClient(RecordingStateClient):
    """Raise one configured publication failure."""

    def __init__(self, failure: BaseException) -> None:
        """Store the failure."""
        super().__init__()
        self.failure = failure

    def set_state(
        self,
        entity_id: str,
        state: str,
        attributes: dict[str, object],
    ) -> None:
        """Raise without recording."""
        raise self.failure


def test_publisher_emits_product_states_then_ok_status() -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantStatusPublisher(client, "0.14.0")
    first = create_product()
    second = replace(
        first,
        id=ProductId(UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")),
        name="Drill",
        image_url="https://example.test/drill.jpg",
    )

    publisher.publish_cycle((first, second), TIMESTAMP, 2, 0)

    assert [call[0] for call in client.calls] == [
        "sensor.price_watch_product_bbbbbbbbbbbb4bbb8bbbbbbbbbbbbbbb",
        "sensor.price_watch_product_dddddddddddd4ddd8ddddddddddddddd",
        "sensor.price_watch_status",
    ]
    first_entity, first_state, first_attributes = client.calls[0]
    assert first_entity.endswith("bbbbbbbbbbbb4bbb8bbbbbbbbbbbbbbb")
    assert first_state == "99.90"
    assert first_attributes == {
        "available": True,
        "device_class": "monetary",
        "friendly_name": "Coffee",
        "last_checked": TIMESTAMP.isoformat(),
        "product_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "unit_of_measurement": "CZK",
        "url": "https://example.test/product",
    }
    assert client.calls[1][2]["entity_picture"] == "https://example.test/drill.jpg"
    assert client.calls[2] == (
        "sensor.price_watch_status",
        "ok",
        {
            "friendly_name": "Price Watch Status",
            "last_checked": TIMESTAMP.isoformat(),
            "notification_count": 2,
            "product_count": 2,
            "provider_error_count": 0,
            "version": "0.14.0",
        },
    )


def test_publisher_marks_provider_error_and_supports_custom_status_id() -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantStatusPublisher(
        client,
        "0.14.0",
        "sensor.price_watch_health",
    )

    publisher.publish_cycle((), TIMESTAMP, 0, 3)

    assert client.calls == [
        (
            "sensor.price_watch_health",
            "provider_error",
            {
                "friendly_name": "Price Watch Status",
                "last_checked": TIMESTAMP.isoformat(),
                "notification_count": 0,
                "product_count": 0,
                "provider_error_count": 3,
                "version": "0.14.0",
            },
        )
    ]


@pytest.mark.parametrize(
    ("arguments", "exception_type", "message"),
    [
        ((object(), "0.14.0"), TypeError, "client"),
        ((RecordingStateClient(), 1), TypeError, "version"),
        ((RecordingStateClient(), " "), ValueError, "version"),
        (
            (RecordingStateClient(), "0.14.0", 1),
            TypeError,
            "status_entity_id",
        ),
        (
            (RecordingStateClient(), "0.14.0", "binary_sensor.price_watch"),
            ValueError,
            "status_entity_id",
        ),
        (
            (RecordingStateClient(), "0.14.0", "sensor.PriceWatch"),
            ValueError,
            "status_entity_id",
        ),
    ],
)
def test_publisher_rejects_invalid_constructor_values(
    arguments: tuple[object, ...],
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        HomeAssistantStatusPublisher(*cast(tuple[object, str, str], arguments))


@pytest.mark.parametrize(
    ("products", "timestamp", "notifications", "errors", "exception_type", "message"),
    [
        ([], TIMESTAMP, 0, 0, TypeError, "products"),
        ((object(),), TIMESTAMP, 0, 0, TypeError, "products"),
        ((), "now", 0, 0, TypeError, "timestamp"),
        ((), datetime(2026, 8, 2, 12, 0), 0, 0, ValueError, "timezone"),
        ((), TIMESTAMP, True, 0, TypeError, "notification_count"),
        ((), TIMESTAMP, "1", 0, TypeError, "notification_count"),
        ((), TIMESTAMP, -1, 0, ValueError, "notification_count"),
        ((), TIMESTAMP, 0, True, TypeError, "provider_error_count"),
        ((), TIMESTAMP, 0, "1", TypeError, "provider_error_count"),
        ((), TIMESTAMP, 0, -1, ValueError, "provider_error_count"),
    ],
)
def test_publisher_validates_complete_call_before_side_effect(
    products: object,
    timestamp: object,
    notifications: object,
    errors: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantStatusPublisher(client, "0.14.0")

    with pytest.raises(exception_type, match=message):
        publisher.publish_cycle(
            cast(tuple[Product, ...], products),
            cast(datetime, timestamp),
            cast(int, notifications),
            cast(int, errors),
        )

    assert client.calls == []


def test_publisher_propagates_client_failure_without_mutable_state() -> None:
    failure = HomeAssistantError("state failed")
    client = FailingStateClient(failure)
    publisher = HomeAssistantStatusPublisher(client, "0.14.0")
    publisher_state = vars(publisher).copy()

    with pytest.raises(HomeAssistantError) as captured:
        publisher.publish_cycle((create_product(),), TIMESTAMP, 0, 0)

    assert captured.value is failure
    assert isinstance(client, HomeAssistantStateClient)
    assert vars(publisher) == publisher_state
