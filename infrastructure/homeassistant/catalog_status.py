"""Publish aggregate Price Watch catalog state to Home Assistant."""

import re
from dataclasses import dataclass
from datetime import datetime

from core.domain import Percentage
from infrastructure.homeassistant.client import HomeAssistantStateClient

_SENSOR_ENTITY_PATTERN = re.compile(r"sensor\.[a-z0-9_]+")
_DEFAULT_ENTITY_ID = "sensor.price_watch_catalog"


@dataclass(frozen=True, slots=True)
class CatalogStatus:
    """Represent one validated aggregate catalog observation."""

    timestamp: datetime
    reference_count: int
    observed_product_count: int
    available_product_count: int
    qualifying_discount_count: int
    minimum_discount: Percentage | None
    last_discovered_at: datetime | None
    last_refresh_attempt_at: datetime | None
    provider_error_count: int
    catalog_error_count: int

    def __post_init__(self) -> None:
        """Validate aggregate counts and chronological values."""
        _validate_timestamp(self.timestamp, "timestamp")
        for name in (
            "reference_count",
            "observed_product_count",
            "available_product_count",
            "qualifying_discount_count",
            "provider_error_count",
            "catalog_error_count",
        ):
            _validate_count(getattr(self, name), name)
        if self.available_product_count > self.observed_product_count:
            raise ValueError("available_product_count cannot exceed observed_product_count")
        if self.qualifying_discount_count > self.available_product_count:
            raise ValueError(
                "qualifying_discount_count cannot exceed available_product_count"
            )
        if self.minimum_discount is not None and not isinstance(
            self.minimum_discount,
            Percentage,
        ):
            raise TypeError("minimum_discount must be a Percentage or None")
        if self.minimum_discount is None and self.qualifying_discount_count:
            raise ValueError(
                "qualifying_discount_count must be zero without minimum_discount"
            )
        _validate_optional_timestamp(
            self.last_discovered_at,
            "last_discovered_at",
        )
        _validate_optional_timestamp(
            self.last_refresh_attempt_at,
            "last_refresh_attempt_at",
        )


class HomeAssistantCatalogStatusPublisher:
    """Publish one deterministic aggregate catalog state representation."""

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
        self._version = _validate_text(version, "version")
        self._entity_id = _validate_entity_id(entity_id)

    def publish(self, status: CatalogStatus) -> None:
        """Publish a fully validated healthy or degraded catalog state."""
        if not isinstance(status, CatalogStatus):
            raise TypeError("status must be a CatalogStatus")
        state = (
            "ok"
            if status.provider_error_count == 0 and status.catalog_error_count == 0
            else "degraded"
        )
        self._client.set_state(
            self._entity_id,
            state,
            {
                "friendly_name": "Price Watch Catalog",
                "last_checked": status.timestamp.isoformat(),
                "reference_count": status.reference_count,
                "observed_product_count": status.observed_product_count,
                "available_product_count": status.available_product_count,
                "qualifying_discount_count": status.qualifying_discount_count,
                "minimum_discount_percentage": (
                    None
                    if status.minimum_discount is None
                    else str(status.minimum_discount.value)
                ),
                "last_discovered_at": _timestamp_text(status.last_discovered_at),
                "last_refresh_attempt_at": _timestamp_text(
                    status.last_refresh_attempt_at
                ),
                "provider_error_count": status.provider_error_count,
                "catalog_error_count": status.catalog_error_count,
                "version": self._version,
            },
        )


def _validate_count(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _validate_timestamp(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _validate_optional_timestamp(value: object, name: str) -> None:
    if value is None:
        return
    _validate_timestamp(value, name)


def _timestamp_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _validate_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} cannot be blank")
    return value


def _validate_entity_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("entity_id must be a string")
    if _SENSOR_ENTITY_PATTERN.fullmatch(value) is None:
        raise ValueError("entity_id must be a lowercase sensor entity ID")
    return value
