"""Unit tests for console notification delivery."""

from types import SimpleNamespace
from typing import TextIO, cast
from unittest import TestCase

from core.notifications import NotificationEngine, NotificationError
from infrastructure.notifications.console import ConsoleNotificationChannel
from tests.unit.notifications.helpers import (
    FlushFailingStream,
    NOTIFICATION_ID,
    RecordingStream,
    WriteFailingStream,
    create_evaluation,
    create_product,
)


class ConsoleNotificationChannelTests(TestCase):
    """Verify deterministic output, validation and delivery failures."""

    def setUp(self) -> None:
        """Create one valid immutable notification."""
        notification = NotificationEngine().generate(
            create_product(),
            create_evaluation(),
            NOTIFICATION_ID,
        )
        if notification is None:
            raise AssertionError("matching evaluation must generate a notification")
        self.notification = notification

    def test_writes_exact_line_and_flushes_stream(self) -> None:
        stream = RecordingStream()
        channel = ConsoleNotificationChannel(cast(TextIO, stream))

        channel.send(self.notification)

        expected = (
            f"{self.notification.created_at.isoformat()} "
            f"{self.notification.product_id.value} "
            f"{self.notification.message}\n"
        )
        self.assertEqual(stream.writes, [expected])
        self.assertEqual(stream.flush_count, 1)

    def test_invalid_stream_raises_type_error(self) -> None:
        invalid_streams = (
            object(),
            SimpleNamespace(write=None, flush=lambda: None),
            SimpleNamespace(write=lambda text: len(text), flush=None),
        )

        for stream in invalid_streams:
            with self.subTest(stream=stream):
                with self.assertRaisesRegex(TypeError, "stream"):
                    ConsoleNotificationChannel(stream)  # type: ignore[arg-type]

    def test_invalid_notification_raises_type_error(self) -> None:
        channel = ConsoleNotificationChannel(
            cast(TextIO, RecordingStream())
        )

        with self.assertRaisesRegex(TypeError, "notification"):
            channel.send("notification")  # type: ignore[arg-type]

    def test_write_failure_is_wrapped_and_preserves_cause(self) -> None:
        channel = ConsoleNotificationChannel(
            cast(TextIO, WriteFailingStream())
        )

        with self.assertRaisesRegex(NotificationError, "delivery failed") as context:
            channel.send(self.notification)

        self.assertIsInstance(context.exception.__cause__, OSError)

    def test_flush_failure_is_wrapped_and_preserves_cause(self) -> None:
        channel = ConsoleNotificationChannel(
            cast(TextIO, FlushFailingStream())
        )

        with self.assertRaisesRegex(NotificationError, "delivery failed") as context:
            channel.send(self.notification)

        self.assertIsInstance(context.exception.__cause__, ValueError)
