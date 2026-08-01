"""Tests for Home Assistant notification delivery."""

from collections.abc import Mapping
from typing import cast

import pytest

from core.domain import Notification
from core.notifications import NotificationEngine, NotificationError
from infrastructure.homeassistant import HomeAssistantError
from infrastructure.notifications.homeassistant import (
    HomeAssistantNotificationChannel,
)
from tests.unit.notifications.helpers import (
    NOTIFICATION_ID,
    create_evaluation,
    create_product,
)


class RecordingClient:
    """Record Home Assistant service calls and optionally raise."""

    def __init__(self, failure: BaseException | None = None) -> None:
        """Configure an optional failure."""
        self.failure = failure
        self.calls: list[tuple[str, str, Mapping[str, object]]] = []

    def call_service(
        self,
        domain: str,
        service: str,
        data: Mapping[str, object],
    ) -> None:
        """Record and then raise the configured failure."""
        self.calls.append((domain, service, data))
        if self.failure is not None:
            raise self.failure


def _notification() -> Notification:
    notification = NotificationEngine().generate(
        create_product(),
        create_evaluation(),
        NOTIFICATION_ID,
    )
    if notification is None:
        raise AssertionError("matching evaluation must create a notification")
    return notification


def test_channel_calls_exact_notify_entity_service() -> None:
    client = RecordingClient()
    channel = HomeAssistantNotificationChannel(
        client,
        "notify.gmail_parkside",
        title="Parkside Price Watch",
    )
    notification = _notification()

    channel.send(notification)

    assert client.calls == [
        (
            "notify",
            "send_message",
            {
                "entity_id": "notify.gmail_parkside",
                "title": "Parkside Price Watch",
                "message": notification.message,
            },
        )
    ]


def test_channel_uses_default_title() -> None:
    client = RecordingClient()

    HomeAssistantNotificationChannel(client, "notify.gmail_parkside").send(
        _notification()
    )

    assert client.calls[0][2]["title"] == "Price Watch"


@pytest.mark.parametrize(
    ("client", "entity_id", "title", "exception_type"),
    [
        (object(), "notify.gmail_parkside", "Price Watch", TypeError),
        (RecordingClient(), 1, "Price Watch", TypeError),
        (RecordingClient(), "", "Price Watch", ValueError),
        (RecordingClient(), "sensor.gmail", "Price Watch", ValueError),
        (RecordingClient(), "notify.Gmail", "Price Watch", ValueError),
        (RecordingClient(), "notify.gmail_parkside", 1, TypeError),
        (RecordingClient(), "notify.gmail_parkside", " ", ValueError),
    ],
)
def test_channel_rejects_invalid_constructor_values(
    client: object,
    entity_id: object,
    title: object,
    exception_type: type[Exception],
) -> None:
    with pytest.raises(exception_type):
        HomeAssistantNotificationChannel(
            cast(object, client),
            cast(str, entity_id),
            cast(str, title),
        )


def test_channel_rejects_invalid_notification_type() -> None:
    with pytest.raises(TypeError):
        HomeAssistantNotificationChannel(
            RecordingClient(),
            "notify.gmail_parkside",
        ).send(cast(Notification, object()))


def test_channel_translates_home_assistant_failure() -> None:
    failure = HomeAssistantError("unavailable")
    channel = HomeAssistantNotificationChannel(
        RecordingClient(failure),
        "notify.gmail_parkside",
    )

    with pytest.raises(NotificationError) as captured:
        channel.send(_notification())

    assert str(captured.value) == "Home Assistant notification delivery failed"
    assert captured.value.__cause__ is failure


@pytest.mark.parametrize("failure", [RuntimeError("bug"), KeyboardInterrupt()])
def test_channel_propagates_unexpected_failure(failure: BaseException) -> None:
    channel = HomeAssistantNotificationChannel(
        RecordingClient(failure),
        "notify.gmail_parkside",
    )

    with pytest.raises(type(failure)) as captured:
        channel.send(_notification())

    assert captured.value is failure
