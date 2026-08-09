"""Publish Price Watch observation storage health to Home Assistant."""

import re
from dataclasses import dataclass
from datetime import datetime

from core.state import ObservationStatistics
from infrastructure.homeassistant.client import HomeAssistantStateClient

_SENSOR_ENTITY_PATTERN = re.compile(r"sensor\.[a-z0-9_]+")
_DEFAULT_ENTITY_ID = "sensor.price_watch_storage"


@dataclass(frozen=True, slots=True)
class StorageStatus:
    """Represent one storage-health check and optional complete statistics."""

    timestamp: datetime
    statistics: ObservationStatistics | None

    def __post_init__(self) -> None:
        """Validate the check timestamp and optional Core statistics value."""
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.statistics is not None and not isinstance(
            self.statistics,
            ObservationStatistics,
        ):
            raise TypeError(
                "statistics must be an ObservationStatistics or None"
            )


class HomeAssistantStorageStatusPublisher:
    """Publish one deterministic observation-storage representation."""

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
        self._version = _validate_text(version)
        self._entity_id = _validate_entity_id(entity_id)

    def publish(self, status: StorageStatus) -> None:
        """Publish validated healthy statistics or a warning state."""
        if not isinstance(status, StorageStatus):
            raise TypeError("status must be a StorageStatus")
        statistics = status.statistics
        attributes: dict[str, object] = {
            "friendly_name": "Price Watch Storage",
            "icon": "mdi:database-check-outline",
            "last_checked": status.timestamp.isoformat(),
            "observation_count": None,
            "observed_product_count": None,
            "first_observation_at": None,
            "last_observation_at": None,
            "storage_size_bytes": None,
            "reclaimable_size_bytes": None,
            "version": self._version,
        }
        state = "warning"
        if statistics is not None:
            state = "ok"
            attributes.update(
                {
                    "observation_count": statistics.observation_count,
                    "observed_product_count": (
                        statistics.observed_product_count
                    ),
                    "first_observation_at": _timestamp_text(
                        statistics.first_observation_at
                    ),
                    "last_observation_at": _timestamp_text(
                        statistics.last_observation_at
                    ),
                    "storage_size_bytes": statistics.storage_size_bytes,
                    "reclaimable_size_bytes": (
                        statistics.reclaimable_size_bytes
                    ),
                }
            )
        self._client.set_state(self._entity_id, state, attributes)


def _timestamp_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _validate_text(value: object) -> str:
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
