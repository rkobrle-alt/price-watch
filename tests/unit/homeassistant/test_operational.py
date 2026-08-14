"""Tests for Home Assistant operational health adapters."""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import cast

import pytest

from core.operations import (
    DailyDigestDelivery,
    OperationalFailureKind,
    OperationalHealthStatus,
    OperationalNotification,
    OperationalNotificationError,
    OperationalNotificationKind,
    OperationalState,
)
from infrastructure.homeassistant import (
    HomeAssistantError,
    HomeAssistantOperationalNotificationChannel,
    HomeAssistantOperationalStatusPublisher,
)
from tests.unit.homeassistant.test_status import RecordingStateClient

NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)


class _ServiceClient:
    def __init__(self, failure: HomeAssistantError | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, str, Mapping[str, object]]] = []

    def call_service(
        self,
        domain: str,
        service: str,
        data: Mapping[str, object],
    ) -> None:
        self.calls.append((domain, service, data))
        if self.failure is not None:
            raise self.failure


def _failed_state() -> OperationalState:
    return OperationalState(
        OperationalHealthStatus.FAILED,
        OperationalFailureKind.PROVIDER_UNAVAILABLE,
        3,
        NOW,
        NOW,
        None,
        True,
        None,
        DailyDigestDelivery(date(2026, 8, 14), NOW, 6, True),
    )


def test_status_publisher_emits_digest_then_health_exactly() -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantOperationalStatusPublisher(client, "0.30.0")

    publisher.publish(_failed_state(), "sent")

    assert client.calls == [
        (
            "sensor.price_watch_daily_digest",
            "2026-08-14",
            {
                "friendly_name": "Price Watch Daily Digest",
                "current_status": "sent",
                "last_sent_at": NOW.isoformat(),
                "product_count": 6,
                "promotion_included": True,
                "version": "0.30.0",
            },
        ),
        (
            "sensor.price_watch_health",
            "failed",
            {
                "friendly_name": "Price Watch Health",
                "failure_kind": "provider_unavailable",
                "consecutive_failure_cycles": 3,
                "incident_started_at": NOW.isoformat(),
                "last_checked_at": NOW.isoformat(),
                "last_recovered_at": None,
                "incident_notified": True,
                "pending_notification": None,
                "version": "0.30.0",
            },
        ),
    ]


def test_status_publisher_represents_initial_state_and_custom_entities() -> None:
    client = RecordingStateClient()
    publisher = HomeAssistantOperationalStatusPublisher(
        client,
        "0.30.0",
        "sensor.custom_health",
        "sensor.custom_digest",
    )

    publisher.publish(OperationalState.initial(), "disabled")

    assert client.calls[0][0:2] == ("sensor.custom_digest", "never")
    assert client.calls[0][2]["last_sent_at"] is None
    assert client.calls[0][2]["product_count"] == 0
    assert client.calls[0][2]["promotion_included"] is False
    assert client.calls[1][0:2] == ("sensor.custom_health", "ok")


@pytest.mark.parametrize(
    ("arguments", "error", "message"),
    [
        ((object(), "1"), TypeError, "client"),
        ((RecordingStateClient(), " "), ValueError, "version"),
        ((RecordingStateClient(), 1), TypeError, "version"),
        ((RecordingStateClient(), "1", "bad"), ValueError, "health_entity_id"),
        ((RecordingStateClient(), "1", 1), TypeError, "health_entity_id"),
        (
            (RecordingStateClient(), "1", "sensor.same", "sensor.same"),
            ValueError,
            "distinct",
        ),
    ],
)
def test_status_publisher_rejects_invalid_construction(
    arguments: tuple[object, ...],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        HomeAssistantOperationalStatusPublisher(*cast(tuple, arguments))


def test_status_publisher_rejects_invalid_publish_arguments() -> None:
    publisher = HomeAssistantOperationalStatusPublisher(
        RecordingStateClient(),
        "1",
    )
    with pytest.raises(TypeError, match="state"):
        publisher.publish(cast(OperationalState, object()), "ok")
    with pytest.raises(TypeError, match="current_digest_status"):
        publisher.publish(OperationalState.initial(), cast(str, 1))
    with pytest.raises(ValueError, match="current_digest_status"):
        publisher.publish(OperationalState.initial(), " ")


def test_notification_channel_delivers_exact_message_and_maps_failure() -> None:
    client = _ServiceClient()
    channel = HomeAssistantOperationalNotificationChannel(
        client,
        "notify.gmail_parkside",
        "Parkside Price Watch",
    )
    notification = OperationalNotification(
        OperationalNotificationKind.FAILURE,
        "failure body",
        NOW,
    )

    channel.send(notification)

    assert client.calls == [
        (
            "notify",
            "send_message",
            {
                "entity_id": "notify.gmail_parkside",
                "title": "Parkside Price Watch Operational Health",
                "message": "failure body",
            },
        )
    ]
    failure = HomeAssistantError("offline")
    failing = HomeAssistantOperationalNotificationChannel(
        _ServiceClient(failure),
        "notify.gmail_parkside",
        "Price Watch",
    )
    with pytest.raises(OperationalNotificationError) as captured:
        failing.send(notification)
    assert captured.value.__cause__ is failure


@pytest.mark.parametrize(
    ("arguments", "error", "message"),
    [
        ((object(), "notify.valid", "title"), TypeError, "client"),
        ((_ServiceClient(), 1, "title"), TypeError, "entity_id"),
        ((_ServiceClient(), "bad", "title"), ValueError, "entity_id"),
        ((_ServiceClient(), "notify.valid", 1), TypeError, "title"),
        ((_ServiceClient(), "notify.valid", " "), ValueError, "title"),
    ],
)
def test_notification_channel_rejects_invalid_construction(
    arguments: tuple[object, ...],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        HomeAssistantOperationalNotificationChannel(*cast(tuple, arguments))


def test_notification_channel_rejects_invalid_notification() -> None:
    channel = HomeAssistantOperationalNotificationChannel(
        _ServiceClient(),
        "notify.valid",
        "title",
    )
    with pytest.raises(TypeError, match="notification"):
        channel.send(cast(OperationalNotification, object()))
