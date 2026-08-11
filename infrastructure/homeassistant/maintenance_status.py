"""Publish a read-only observation-retention preview to Home Assistant."""

import re
from dataclasses import dataclass
from datetime import datetime

from core.state import ObservationRetentionPlan
from infrastructure.homeassistant.client import HomeAssistantStateClient

_SENSOR_ENTITY_PATTERN = re.compile(r"sensor\.[a-z0-9_]+")
_DEFAULT_ENTITY_ID = "sensor.price_watch_maintenance"


@dataclass(frozen=True, slots=True)
class MaintenanceStatus:
    """Represent one checked, read-only observation-retention plan."""

    timestamp: datetime
    retention_days: int
    plan: ObservationRetentionPlan
    apply_available: bool = False

    def __post_init__(self) -> None:
        """Validate the complete immutable maintenance representation."""
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if isinstance(self.retention_days, bool) or not isinstance(
            self.retention_days,
            int,
        ):
            raise TypeError("retention_days must be an int")
        if self.retention_days <= 0:
            raise ValueError("retention_days must be positive")
        if not isinstance(self.plan, ObservationRetentionPlan):
            raise TypeError("plan must be an ObservationRetentionPlan")
        if not isinstance(self.apply_available, bool):
            raise TypeError("apply_available must be a bool")


class HomeAssistantMaintenanceStatusPublisher:
    """Publish one deterministic retention preview without applying it."""

    def __init__(
        self,
        client: HomeAssistantStateClient,
        version: str,
        entity_id: str = _DEFAULT_ENTITY_ID,
    ) -> None:
        """Configure an injected state client and stable entity identity."""
        if not isinstance(client, HomeAssistantStateClient):
            raise TypeError("client must implement HomeAssistantStateClient")
        self._client = client
        self._version = _validate_version(version)
        self._entity_id = _validate_entity_id(entity_id)

    def publish(self, status: MaintenanceStatus) -> None:
        """Publish exact plan counts as a read-only sensor representation."""
        if not isinstance(status, MaintenanceStatus):
            raise TypeError("status must be a MaintenanceStatus")
        plan = status.plan
        self._client.set_state(
            self._entity_id,
            str(plan.removable_observation_count),
            {
                "friendly_name": "Price Watch Maintenance",
                "icon": "mdi:database-eye-outline",
                "last_checked": status.timestamp.isoformat(),
                "retention_days": status.retention_days,
                "cutoff": plan.cutoff.isoformat(),
                "observation_count": plan.observation_count,
                "removable_observation_count": (
                    plan.removable_observation_count
                ),
                "retained_observation_count": plan.retained_observation_count,
                "protected_observation_count": (
                    plan.protected_observation_count
                ),
                "apply_available": status.apply_available,
                "version": self._version,
            },
        )


def _validate_version(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("version must be a string")
    if not value.strip():
        raise ValueError("version cannot be blank")
    return value


def _validate_entity_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("entity_id must be a string")
    if _SENSOR_ENTITY_PATTERN.fullmatch(value) is None:
        raise ValueError("entity_id must be a lowercase sensor entity ID")
    return value
