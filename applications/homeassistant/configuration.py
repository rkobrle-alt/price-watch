"""Pure Home Assistant App option validation."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from applications.configuration import ApplicationConfig, parse_configuration
from core.configuration import ConfigurationError

_ALLOWED_KEYS = frozenset(
    {
        "product_urls",
        "notify_entity",
        "interval_seconds",
        "timeout_seconds",
        "price_drop_percentage",
        "price_drop_amount",
        "notification_title",
    }
)
_REQUIRED_KEYS = frozenset(
    {"product_urls", "notify_entity", "interval_seconds"}
)
_ENTITY_PATTERN = re.compile(r"notify\.[a-z0-9_]+")


@dataclass(frozen=True, slots=True)
class HomeAssistantConfig:
    """Configure the Supervisor-hosted Price Watch composition."""

    application: ApplicationConfig
    notify_entity: str
    notification_title: str = "Price Watch"

    def __post_init__(self) -> None:
        """Validate member types and Home Assistant-specific invariants."""
        if not isinstance(self.application, ApplicationConfig):
            raise TypeError("application must be an ApplicationConfig")
        if self.application.interval is None:
            raise ValueError("application.interval is required")
        if not isinstance(self.notify_entity, str):
            raise TypeError("notify_entity must be a string")
        if _ENTITY_PATTERN.fullmatch(self.notify_entity) is None:
            raise ValueError("notify_entity must match notify.<object_id>")
        if not isinstance(self.notification_title, str):
            raise TypeError("notification_title must be a string")
        if not self.notification_title.strip():
            raise ValueError("notification_title cannot be blank")


def parse_homeassistant_options(
    document: Mapping[str, object],
    data_directory: Path,
) -> HomeAssistantConfig:
    """Convert strict Supervisor App options into immutable configuration."""
    if not isinstance(document, Mapping):
        raise TypeError("document must be a Mapping")
    if not isinstance(data_directory, Path):
        raise TypeError("data_directory must be a Path")
    _validate_keys(document)

    lidl: dict[str, object] = {"product_urls": document["product_urls"]}
    if "timeout_seconds" in document:
        lidl["timeout_seconds"] = document["timeout_seconds"]
    price_drop: dict[str, object] = {}
    if "price_drop_percentage" in document:
        price_drop["percentage"] = document["price_drop_percentage"]
    if "price_drop_amount" in document:
        price_drop["fixed_amount"] = document["price_drop_amount"]
    application_document: dict[str, object] = {
        "schema_version": 1,
        "provider": {"lidl": lidl},
        "state": {"file": "state.json"},
        "scheduler": {"interval_seconds": document["interval_seconds"]},
    }
    if price_drop:
        application_document["rules"] = {"price_drop": price_drop}

    application = parse_configuration(application_document, data_directory)
    try:
        return HomeAssistantConfig(
            application=application,
            notify_entity=cast(str, document["notify_entity"]),
            notification_title=cast(
                str,
                document.get("notification_title", "Price Watch"),
            ),
        )
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f"Home Assistant options are invalid: {error}"
        ) from error


def _validate_keys(document: Mapping[object, object]) -> None:
    if not all(isinstance(key, str) for key in document):
        raise ConfigurationError("Home Assistant option keys must be strings")
    keys = cast(set[str], set(document))
    unknown = keys - _ALLOWED_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationError(f"Home Assistant options contain unknown keys: {names}")
    missing = _REQUIRED_KEYS - keys
    if missing:
        names = ", ".join(sorted(missing))
        raise ConfigurationError(f"Home Assistant options are missing keys: {names}")
