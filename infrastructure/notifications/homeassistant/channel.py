"""Notification delivery through a Home Assistant notify entity."""

import re
from typing import cast

from core.domain import Notification
from core.notifications import NotificationError
from infrastructure.homeassistant import HomeAssistantClient, HomeAssistantError

_ENTITY_PATTERN = re.compile(r"notify\.[a-z0-9_]+")


class HomeAssistantNotificationChannel:
    """Delegate immutable notifications to Home Assistant Core."""

    def __init__(
        self,
        client: HomeAssistantClient,
        entity_id: str,
        title: str = "Price Watch",
    ) -> None:
        """Configure the injected client and explicit notify entity."""
        if not callable(getattr(client, "call_service", None)):
            raise TypeError("client must expose a callable call_service method")
        if not isinstance(entity_id, str):
            raise TypeError("entity_id must be a string")
        if _ENTITY_PATTERN.fullmatch(entity_id) is None:
            raise ValueError("entity_id must match notify.<object_id>")
        if not isinstance(title, str):
            raise TypeError("title must be a string")
        if not title.strip():
            raise ValueError("title cannot be blank")
        self._client = cast(HomeAssistantClient, client)
        self._entity_id = entity_id
        self._title = title

    def send(self, notification: Notification) -> None:
        """Deliver one notification through `notify.send_message`."""
        if not isinstance(notification, Notification):
            raise TypeError("notification must be a Notification")
        try:
            self._client.call_service(
                "notify",
                "send_message",
                {
                    "entity_id": self._entity_id,
                    "title": self._title,
                    "message": notification.message,
                },
            )
        except HomeAssistantError as error:
            raise NotificationError(
                "Home Assistant notification delivery failed"
            ) from error
