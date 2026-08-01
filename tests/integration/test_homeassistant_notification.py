"""Integration test for Domain-to-Home-Assistant notification delivery."""

import json
from contextlib import AbstractContextManager
from io import BytesIO
from typing import BinaryIO, cast
from urllib.request import Request

from core.notifications import NotificationEngine
from infrastructure.homeassistant import UrllibHomeAssistantClient
from infrastructure.notifications.homeassistant import HomeAssistantNotificationChannel
from tests.unit.notifications.helpers import (
    NOTIFICATION_ID,
    create_evaluation,
    create_product,
)


class SuccessfulResponse(AbstractContextManager[BinaryIO]):
    """Provide a readable successful HTTP response."""

    def __init__(self) -> None:
        """Create the deterministic response body."""
        self._body = BytesIO(b"[]")

    def __enter__(self) -> BinaryIO:
        """Return this response as a readable stream."""
        return cast(BinaryIO, self)

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> None:
        """Complete the context without suppressing failures."""

    def read(self, size: int = -1) -> bytes:
        """Read the response body."""
        return self._body.read(size)


class CapturingOpener:
    """Capture the final request without network access."""

    def __init__(self) -> None:
        """Initialize empty request state."""
        self.request: Request | None = None
        self.timeout: int | None = None

    def __call__(
        self,
        request: Request,
        *,
        timeout: int,
    ) -> AbstractContextManager[BinaryIO]:
        """Capture the request and return a successful response."""
        self.request = request
        self.timeout = timeout
        return SuccessfulResponse()


def test_domain_notification_reaches_home_assistant_rest_boundary() -> None:
    """Verify the complete deterministic notification delivery path."""
    opener = CapturingOpener()
    client = UrllibHomeAssistantClient(
        "http://supervisor/core/api",
        "injected-token",
        timeout_seconds=9,
        opener=opener,
    )
    channel = HomeAssistantNotificationChannel(
        client,
        "notify.gmail_parkside",
        title="Parkside Price Watch",
    )
    notification = NotificationEngine().generate(
        create_product(),
        create_evaluation(),
        NOTIFICATION_ID,
    )

    assert notification is not None
    channel.send(notification)

    assert opener.request is not None
    assert opener.timeout == 9
    assert opener.request.full_url == (
        "http://supervisor/core/api/services/notify/send_message"
    )
    assert opener.request.get_header("Authorization") == "Bearer injected-token"
    assert opener.request.data is not None
    assert json.loads(opener.request.data) == {
        "entity_id": "notify.gmail_parkside",
        "message": (
            "Product price decreased.\n"
            "Product: Coffee\n"
            "Current price: 99.90 CZK\n"
            "Availability: available\n"
            "URL: https://example.test/product"
        ),
        "title": "Parkside Price Watch",
    }
