"""Publish Price Watch cycle state to Home Assistant."""

import re
from collections.abc import Mapping
from datetime import datetime

from core.domain import Product
from infrastructure.homeassistant.client import HomeAssistantStateClient

_SENSOR_ENTITY_PATTERN = re.compile(r"sensor\.[a-z0-9_]+")
_DEFAULT_STATUS_ENTITY_ID = "sensor.price_watch_status"


class HomeAssistantStatusPublisher:
    """Publish deterministic cycle and product state representations."""

    def __init__(
        self,
        client: HomeAssistantStateClient,
        version: str,
        status_entity_id: str = _DEFAULT_STATUS_ENTITY_ID,
    ) -> None:
        """Configure the injected state client and stable status identity."""
        if not isinstance(client, HomeAssistantStateClient):
            raise TypeError("client must implement HomeAssistantStateClient")
        self._client = client
        self._version = _validate_text(version, "version")
        self._status_entity_id = _validate_entity_id(status_entity_id)

    def publish_cycle(
        self,
        products: tuple[Product, ...],
        timestamp: datetime,
        notification_count: int,
        provider_error_count: int,
    ) -> None:
        """Publish validated product states followed by the cycle status."""
        _validate_products(products)
        _validate_timestamp(timestamp)
        _validate_count(notification_count, "notification_count")
        _validate_count(provider_error_count, "provider_error_count")

        timestamp_text = timestamp.isoformat()
        publications = tuple(
            _product_publication(product, timestamp_text) for product in products
        )
        for entity_id, state, attributes in publications:
            self._client.set_state(entity_id, state, attributes)

        status = "ok" if provider_error_count == 0 else "provider_error"
        self._client.set_state(
            self._status_entity_id,
            status,
            {
                "friendly_name": "Price Watch Status",
                "last_checked": timestamp_text,
                "notification_count": notification_count,
                "product_count": len(products),
                "provider_error_count": provider_error_count,
                "version": self._version,
            },
        )


def _product_publication(
    product: Product,
    timestamp_text: str,
) -> tuple[str, str, Mapping[str, object]]:
    attributes: dict[str, object] = {
        "available": product.availability,
        "device_class": "monetary",
        "friendly_name": product.name,
        "last_checked": timestamp_text,
        "product_id": str(product.id.value),
        "unit_of_measurement": product.currency.value,
        "url": product.url,
    }
    if product.image_url is not None:
        attributes["entity_picture"] = product.image_url
    entity_id = f"sensor.price_watch_product_{product.id.value.hex}"
    return entity_id, str(product.current_price.amount), attributes


def _validate_products(value: object) -> None:
    if not isinstance(value, tuple):
        raise TypeError("products must be a tuple")
    if not all(isinstance(product, Product) for product in value):
        raise TypeError("products must contain only Product instances")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")


def _validate_count(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _validate_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} cannot be blank")
    return value


def _validate_entity_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("status_entity_id must be a string")
    if _SENSOR_ENTITY_PATTERN.fullmatch(value) is None:
        raise ValueError("status_entity_id must be a lowercase sensor entity ID")
    return value
