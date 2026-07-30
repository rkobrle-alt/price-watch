"""Public API tests for notification packages."""

from typing import TextIO, cast
from unittest import TestCase

import core.notifications as notifications_api
import infrastructure.notifications as infrastructure_notifications
import infrastructure.notifications.console as console_api
from core.notifications import NotificationChannel, NotificationError
from infrastructure.notifications.console import ConsoleNotificationChannel
from tests.unit.notifications.helpers import RecordingStream


class NotificationPublicApiTests(TestCase):
    """Verify documented exports and Protocol compatibility."""

    def test_core_notifications_exports(self) -> None:
        expected = {
            "NotificationChannel",
            "NotificationEngine",
            "NotificationError",
        }

        self.assertEqual(set(notifications_api.__all__), expected)
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue(getattr(notifications_api, name).__doc__)

    def test_console_notifications_exports(self) -> None:
        self.assertEqual(console_api.__all__, ["ConsoleNotificationChannel"])
        self.assertIs(
            console_api.ConsoleNotificationChannel,
            ConsoleNotificationChannel,
        )
        self.assertTrue(infrastructure_notifications.__doc__)

    def test_console_channel_satisfies_protocol(self) -> None:
        concrete = ConsoleNotificationChannel(cast(TextIO, RecordingStream()))
        channel: NotificationChannel = concrete

        self.assertIs(channel, concrete)

    def test_notification_error_is_an_exception(self) -> None:
        self.assertIsInstance(NotificationError("delivery failed"), Exception)
