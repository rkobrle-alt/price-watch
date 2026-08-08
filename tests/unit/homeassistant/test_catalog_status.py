"""Tests for Home Assistant aggregate catalog state publication."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import cast

import pytest

from core.domain import Percentage
from infrastructure.homeassistant import (
    CatalogStatus,
    HomeAssistantCatalogStatusPublisher,
    HomeAssistantError,
)
from tests.unit.homeassistant.test_status import (
    FailingStateClient,
    RecordingStateClient,
)
from tests.unit.homeassistant_app.helpers import TIMESTAMP


def _status() -> CatalogStatus:
    return CatalogStatus(
        timestamp=TIMESTAMP,
        reference_count=1879,
        observed_product_count=125,
        available_product_count=100,
        qualifying_discount_count=8,
        minimum_discount=Percentage(Decimal("20.00")),
        last_discovered_at=TIMESTAMP,
        last_refresh_attempt_at=TIMESTAMP,
        provider_error_count=0,
        catalog_error_count=0,
        notification_count=2,
        suppressed_notification_count=3,
    )


def test_publisher_emits_exact_healthy_catalog_representation() -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantCatalogStatusPublisher(client, "0.21.0")

    publisher.publish(_status())

    assert client.calls == [
        (
            "sensor.price_watch_discounted_products",
            "8",
            {
                "friendly_name": "Parkside Discounted Products",
                "icon": "mdi:percent",
                "unit_of_measurement": "products",
                "last_checked": TIMESTAMP.isoformat(),
                "reference_count": 1879,
                "observed_product_count": 125,
                "available_product_count": 100,
                "minimum_discount_percentage": "20.00",
                "notification_count": 2,
                "suppressed_notification_count": 3,
                "version": "0.21.0",
            },
        ),
        (
            "sensor.price_watch_catalog_errors",
            "0",
            {
                "friendly_name": "Price Watch Catalog Errors",
                "icon": "mdi:alert-circle-outline",
                "unit_of_measurement": "errors",
                "last_checked": TIMESTAMP.isoformat(),
                "provider_error_count": 0,
                "catalog_error_count": 0,
                "version": "0.21.0",
            },
        ),
        (
            "sensor.price_watch_last_checked",
            TIMESTAMP.isoformat(),
            {
                "friendly_name": "Price Watch Last Checked",
                "device_class": "timestamp",
                "icon": "mdi:clock-check-outline",
                "last_checked": TIMESTAMP.isoformat(),
                "catalog_health": "ok",
                "version": "0.21.0",
            },
        ),
        (
            "sensor.price_watch_catalog",
            "ok",
            {
                "friendly_name": "Price Watch Catalog",
                "last_checked": TIMESTAMP.isoformat(),
                "reference_count": 1879,
                "observed_product_count": 125,
                "available_product_count": 100,
                "qualifying_discount_count": 8,
                "minimum_discount_percentage": "20.00",
                "last_discovered_at": TIMESTAMP.isoformat(),
                "last_refresh_attempt_at": TIMESTAMP.isoformat(),
                "provider_error_count": 0,
                "catalog_error_count": 0,
                "notification_count": 2,
                "suppressed_notification_count": 3,
                "version": "0.21.0",
            },
        )
    ]


def test_publisher_emits_degraded_state_and_unknown_optional_values() -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantCatalogStatusPublisher(
        client,
        "0.21.0",
        "sensor.price_watch_catalog_health",
    )

    publisher.publish(
        replace(
            _status(),
            qualifying_discount_count=0,
            minimum_discount=None,
            last_discovered_at=None,
            last_refresh_attempt_at=None,
            provider_error_count=1,
            catalog_error_count=1,
        )
    )

    discounted_id, discounted_state, discounted_attributes = client.calls[0]
    assert discounted_id == "sensor.price_watch_discounted_products"
    assert discounted_state == "0"
    assert discounted_attributes["minimum_discount_percentage"] is None
    error_id, error_state, error_attributes = client.calls[1]
    assert error_id == "sensor.price_watch_catalog_errors"
    assert error_state == "2"
    assert error_attributes["provider_error_count"] == 1
    assert error_attributes["catalog_error_count"] == 1
    assert client.calls[2][2]["catalog_health"] == "degraded"
    entity_id, state, attributes = client.calls[3]
    assert entity_id == "sensor.price_watch_catalog_health"
    assert state == "degraded"
    assert attributes["minimum_discount_percentage"] is None
    assert attributes["last_discovered_at"] is None
    assert attributes["last_refresh_attempt_at"] is None


@pytest.mark.parametrize(
    ("arguments", "exception_type", "message"),
    [
        ((object(), "0.21.0"), TypeError, "client"),
        ((RecordingStateClient(), 1), TypeError, "version"),
        ((RecordingStateClient(), " "), ValueError, "version"),
        (
            (RecordingStateClient(), "0.21.0", 1),
            TypeError,
            "entity_id",
        ),
        (
            (RecordingStateClient(), "0.21.0", "binary_sensor.catalog"),
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
        HomeAssistantCatalogStatusPublisher(
            *cast(tuple[object, str, str], arguments)
        )


@pytest.mark.parametrize(
    ("changes", "exception_type", "message"),
    [
        ({"timestamp": "now"}, TypeError, "timestamp"),
        (
            {"timestamp": datetime(2026, 8, 8, 10, 0)},
            ValueError,
            "timezone",
        ),
        ({"reference_count": True}, TypeError, "reference_count"),
        ({"observed_product_count": "1"}, TypeError, "observed_product_count"),
        ({"provider_error_count": -1}, ValueError, "provider_error_count"),
        ({"available_product_count": 126}, ValueError, "available_product_count"),
        ({"qualifying_discount_count": 101}, ValueError, "qualifying_discount_count"),
        ({"minimum_discount": object()}, TypeError, "minimum_discount"),
        ({"notification_count": True}, TypeError, "notification_count"),
        (
            {"suppressed_notification_count": -1},
            ValueError,
            "suppressed_notification_count",
        ),
        (
            {"minimum_discount": None, "qualifying_discount_count": 1},
            ValueError,
            "without minimum_discount",
        ),
        ({"last_discovered_at": "now"}, TypeError, "last_discovered_at"),
        (
            {"last_refresh_attempt_at": datetime(2026, 8, 8, 10, 0)},
            ValueError,
            "last_refresh_attempt_at",
        ),
    ],
)
def test_catalog_status_rejects_invalid_values(
    changes: dict[str, object],
    exception_type: type[Exception],
    message: str,
) -> None:
    values = {
        "timestamp": _status().timestamp,
        "reference_count": _status().reference_count,
        "observed_product_count": _status().observed_product_count,
        "available_product_count": _status().available_product_count,
        "qualifying_discount_count": _status().qualifying_discount_count,
        "minimum_discount": _status().minimum_discount,
        "last_discovered_at": _status().last_discovered_at,
        "last_refresh_attempt_at": _status().last_refresh_attempt_at,
        "provider_error_count": _status().provider_error_count,
        "catalog_error_count": _status().catalog_error_count,
        "notification_count": _status().notification_count,
        "suppressed_notification_count": _status().suppressed_notification_count,
    }
    values.update(changes)

    with pytest.raises(exception_type, match=message):
        CatalogStatus(**cast(dict, values))


def test_publisher_rejects_invalid_status_before_side_effect() -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantCatalogStatusPublisher(client, "0.21.0")

    with pytest.raises(TypeError, match="status"):
        publisher.publish(cast(CatalogStatus, object()))

    assert client.calls == []


def test_publisher_propagates_home_assistant_failure() -> None:
    failure = HomeAssistantError("state failed")
    publisher = HomeAssistantCatalogStatusPublisher(
        FailingStateClient(failure),
        "0.21.0",
    )

    with pytest.raises(HomeAssistantError) as captured:
        publisher.publish(_status())

    assert captured.value is failure
