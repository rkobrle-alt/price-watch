"""Tests for Home Assistant daily digest delivery."""

from datetime import UTC, date, datetime
from typing import cast

import pytest

from core.notifications import DailyDiscountDigest, NotificationError
from infrastructure.homeassistant import HomeAssistantError
from infrastructure.notifications.homeassistant import (
    HomeAssistantDailyDiscountDigestChannel,
)
from tests.unit.homeassistant.test_notification_channel import RecordingClient


def _digest() -> DailyDiscountDigest:
    return DailyDiscountDigest(
        date(2026, 8, 8),
        datetime(2026, 8, 8, 6, tzinfo=UTC),
        (),
        "Daily digest",
    )


def test_digest_channel_calls_exact_notify_service_and_default_title() -> None:
    client = RecordingClient()
    channel = HomeAssistantDailyDiscountDigestChannel(
        client,
        "notify.gmail_parkside",
    )

    channel.send(_digest())

    assert client.calls == [
        (
            "notify",
            "send_message",
            {
                "entity_id": "notify.gmail_parkside",
                "title": "Price Watch Daily Digest",
                "message": "Daily digest",
            },
        )
    ]


@pytest.mark.parametrize(
    ("client", "entity_id", "title", "error"),
    [
        (object(), "notify.gmail", "Digest", TypeError),
        (RecordingClient(), 1, "Digest", TypeError),
        (RecordingClient(), "", "Digest", ValueError),
        (RecordingClient(), "sensor.gmail", "Digest", ValueError),
        (RecordingClient(), "notify.Gmail", "Digest", ValueError),
        (RecordingClient(), "notify.gmail", 1, TypeError),
        (RecordingClient(), "notify.gmail", " ", ValueError),
    ],
)
def test_digest_channel_rejects_invalid_constructor_values(
    client: object,
    entity_id: object,
    title: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        HomeAssistantDailyDiscountDigestChannel(
            cast(object, client),
            cast(str, entity_id),
            cast(str, title),
        )


def test_digest_channel_rejects_invalid_digest_type() -> None:
    with pytest.raises(TypeError, match="digest"):
        HomeAssistantDailyDiscountDigestChannel(
            RecordingClient(),
            "notify.gmail",
        ).send(cast(DailyDiscountDigest, object()))


def test_digest_channel_translates_only_home_assistant_failures() -> None:
    failure = HomeAssistantError("unavailable")
    channel = HomeAssistantDailyDiscountDigestChannel(
        RecordingClient(failure),
        "notify.gmail",
        "Digest",
    )

    with pytest.raises(NotificationError) as captured:
        channel.send(_digest())
    assert captured.value.__cause__ is failure

    bug = RuntimeError("bug")
    with pytest.raises(RuntimeError) as captured_bug:
        HomeAssistantDailyDiscountDigestChannel(
            RecordingClient(bug),
            "notify.gmail",
        ).send(_digest())
    assert captured_bug.value is bug
