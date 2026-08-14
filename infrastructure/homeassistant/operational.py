"""Publish and deliver Price Watch operational health information."""

import re
from datetime import datetime
from enum import Enum
from typing import cast

from core.operations import (
    OperationalNotification,
    OperationalNotificationError,
    OperationalState,
)
from infrastructure.homeassistant.client import (
    HomeAssistantClient,
    HomeAssistantStateClient,
)
from infrastructure.homeassistant.exceptions import HomeAssistantError

_SENSOR_PATTERN = re.compile(r"sensor\.[a-z0-9_]+")
_NOTIFY_PATTERN = re.compile(r"notify\.[a-z0-9_]+")
_HEALTH_ENTITY = "sensor.price_watch_health"
_DIGEST_ENTITY = "sensor.price_watch_daily_digest"


class HomeAssistantOperationalStatusPublisher:
    """Publish durable health and daily-digest diagnostics."""

    def __init__(
        self,
        client: HomeAssistantStateClient,
        version: str,
        health_entity_id: str = _HEALTH_ENTITY,
        digest_entity_id: str = _DIGEST_ENTITY,
    ) -> None:
        """Configure the injected client and stable entity identities."""
        if not isinstance(client, HomeAssistantStateClient):
            raise TypeError("client must implement HomeAssistantStateClient")
        self._client = client
        self._version = _validate_text(version, "version")
        self._health_entity_id = _validate_sensor(
            health_entity_id,
            "health_entity_id",
        )
        self._digest_entity_id = _validate_sensor(
            digest_entity_id,
            "digest_entity_id",
        )
        if self._health_entity_id == self._digest_entity_id:
            raise ValueError("operational entity IDs must be distinct")

    def publish(
        self,
        state: OperationalState,
        current_digest_status: str,
    ) -> None:
        """Publish digest diagnostics before the authoritative health state."""
        if not isinstance(state, OperationalState):
            raise TypeError("state must be an OperationalState")
        digest_status = _validate_text(
            current_digest_status,
            "current_digest_status",
        )
        delivery = state.last_digest_delivery
        self._client.set_state(
            self._digest_entity_id,
            "never" if delivery is None else delivery.calendar_date.isoformat(),
            {
                "friendly_name": "Price Watch Daily Digest",
                "current_status": digest_status,
                "last_sent_at": (
                    None if delivery is None else delivery.delivered_at.isoformat()
                ),
                "product_count": 0 if delivery is None else delivery.product_count,
                "promotion_included": (
                    False if delivery is None else delivery.promotion_included
                ),
                "version": self._version,
            },
        )
        self._client.set_state(
            self._health_entity_id,
            state.status.value,
            {
                "friendly_name": "Price Watch Health",
                "failure_kind": _enum_value(state.failure_kind),
                "consecutive_failure_cycles": state.consecutive_failure_cycles,
                "incident_started_at": _timestamp_text(state.incident_started_at),
                "last_checked_at": _timestamp_text(state.last_checked_at),
                "last_recovered_at": _timestamp_text(state.last_recovered_at),
                "incident_notified": state.incident_notified,
                "pending_notification": _enum_value(state.pending_notification),
                "version": self._version,
            },
        )


class HomeAssistantOperationalNotificationChannel:
    """Deliver operational transition messages through Home Assistant."""

    def __init__(
        self,
        client: HomeAssistantClient,
        entity_id: str,
        title: str,
    ) -> None:
        """Configure the existing notify entity and operational title."""
        if not isinstance(client, HomeAssistantClient):
            raise TypeError("client must implement HomeAssistantClient")
        if not isinstance(entity_id, str):
            raise TypeError("entity_id must be a string")
        if _NOTIFY_PATTERN.fullmatch(entity_id) is None:
            raise ValueError("entity_id must match notify.<object_id>")
        self._client = cast(HomeAssistantClient, client)
        self._entity_id = entity_id
        self._title = f"{_validate_text(title, 'title')} Operational Health"

    def send(self, notification: OperationalNotification) -> None:
        """Deliver one operational message unchanged."""
        if not isinstance(notification, OperationalNotification):
            raise TypeError("notification must be an OperationalNotification")
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
            raise OperationalNotificationError(
                "Home Assistant operational notification delivery failed"
            ) from error


def _validate_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} cannot be blank")
    return value


def _validate_sensor(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if _SENSOR_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase sensor entity ID")
    return value


def _timestamp_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _enum_value(value: Enum | None) -> str | None:
    return None if value is None else str(value.value)
