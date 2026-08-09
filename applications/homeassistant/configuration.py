"""Pure Home Assistant App option validation."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from applications.catalog_monitoring import CatalogMonitoringConfig
from applications.daily_digest import DailyDigestConfig
from applications.configuration import ApplicationConfig, parse_configuration
from core.configuration import ConfigurationError
from core.domain import Percentage

_ALLOWED_KEYS = frozenset(
    {
        "product_urls",
        "notify_entity",
        "interval_seconds",
        "timeout_seconds",
        "price_drop_percentage",
        "price_drop_amount",
        "notification_title",
        "catalog_enabled",
        "catalog_batch_size",
        "catalog_discovery_interval_cycles",
        "daily_digest_enabled",
        "daily_digest_time",
        "individual_notifications_enabled",
        "retention_preview_days",
    }
)
_REQUIRED_KEYS = frozenset({"notify_entity", "interval_seconds"})
_CATALOG_ONLY_KEYS = frozenset(
    {
        "catalog_batch_size",
        "catalog_discovery_interval_cycles",
        "daily_digest_enabled",
        "daily_digest_time",
        "individual_notifications_enabled",
        "retention_preview_days",
    }
)
_ENTITY_PATTERN = re.compile(r"notify\.[a-z0-9_]+")
_TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


@dataclass(frozen=True, slots=True)
class HomeAssistantConfig:
    """Configure one explicit or catalog Supervisor-hosted composition."""

    application: ApplicationConfig | None
    notify_entity: str
    notification_title: str = "Price Watch"
    catalog: CatalogMonitoringConfig | None = None
    daily_digest: DailyDigestConfig | None = None
    individual_notifications_enabled: bool = True
    retention_preview_days: int | None = None

    def __post_init__(self) -> None:
        """Validate mode selection and Home Assistant-specific invariants."""
        if self.application is not None and not isinstance(
            self.application,
            ApplicationConfig,
        ):
            raise TypeError("application must be an ApplicationConfig or None")
        if self.catalog is not None and not isinstance(
            self.catalog,
            CatalogMonitoringConfig,
        ):
            raise TypeError("catalog must be a CatalogMonitoringConfig or None")
        if (self.application is None) == (self.catalog is None):
            raise ValueError("exactly one monitoring mode must be configured")
        if self.daily_digest is not None and not isinstance(
            self.daily_digest,
            DailyDigestConfig,
        ):
            raise TypeError("daily_digest must be a DailyDigestConfig or None")
        if self.daily_digest is not None and self.catalog is None:
            raise ValueError("daily digest requires catalog monitoring")
        if not isinstance(self.individual_notifications_enabled, bool):
            raise TypeError("individual_notifications_enabled must be a boolean")
        if not self.individual_notifications_enabled and self.catalog is None:
            raise ValueError("disabled individual notifications require catalog monitoring")
        if self.retention_preview_days is not None:
            _positive_integer(self.retention_preview_days, "retention_preview_days")
            if self.catalog is None:
                raise ValueError("retention preview requires catalog monitoring")
        if self.application is not None and self.application.interval is None:
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
    catalog_enabled = document.get("catalog_enabled", False)
    if not isinstance(catalog_enabled, bool):
        raise ConfigurationError("catalog_enabled must be a boolean")
    _validate_keys(document)

    try:
        if catalog_enabled:
            application = None
            catalog = _parse_catalog_configuration(document, data_directory)
        else:
            application = _parse_explicit_configuration(document, data_directory)
            catalog = None
        daily_digest = _parse_daily_digest(document, catalog)
        return HomeAssistantConfig(
            application=application,
            catalog=catalog,
            notify_entity=cast(str, document["notify_entity"]),
            notification_title=cast(
                str,
                document.get("notification_title", "Price Watch"),
            ),
            daily_digest=daily_digest,
            individual_notifications_enabled=cast(
                bool,
                document.get("individual_notifications_enabled", True),
            ),
            retention_preview_days=(
                None
                if "retention_preview_days" not in document
                else _positive_integer(
                    document["retention_preview_days"],
                    "retention_preview_days",
                )
            ),
        )
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f"Home Assistant options are invalid: {error}"
        ) from error


def _parse_explicit_configuration(
    document: Mapping[str, object],
    data_directory: Path,
) -> ApplicationConfig:
    catalog_keys = set(document) & _CATALOG_ONLY_KEYS
    if catalog_keys:
        names = ", ".join(sorted(catalog_keys))
        raise ConfigurationError(
            f"catalog options require catalog_enabled: {names}"
        )
    lidl: dict[str, object] = {"product_urls": document["product_urls"]}
    if "timeout_seconds" in document:
        lidl["timeout_seconds"] = document["timeout_seconds"]
    application_document = _application_document(document, lidl, "state.json")
    return parse_configuration(application_document, data_directory)


def _parse_catalog_configuration(
    document: Mapping[str, object],
    data_directory: Path,
) -> CatalogMonitoringConfig:
    if "product_urls" in document and document["product_urls"] != []:
        raise ConfigurationError(
            "product_urls cannot be combined with catalog_enabled"
        )
    interval = timedelta(
        seconds=_positive_integer(document["interval_seconds"], "interval_seconds")
    )
    timeout = _positive_integer(document.get("timeout_seconds", 10), "timeout_seconds")
    batch_size = _positive_integer(
        document.get("catalog_batch_size", 25),
        "catalog_batch_size",
    )
    discovery_cycles = _positive_integer(
        document.get("catalog_discovery_interval_cycles", 288),
        "catalog_discovery_interval_cycles",
    )
    return CatalogMonitoringConfig(
        database_file=data_directory / "catalog.sqlite3",
        interval=interval,
        timeout_seconds=timeout,
        batch_size=batch_size,
        discovery_interval_cycles=discovery_cycles,
        price_drop_percentage=_optional_decimal(
            document.get("price_drop_percentage", "20.00"),
            "price_drop_percentage",
            Decimal("100"),
        ),
        price_drop_amount=_optional_decimal(
            document.get("price_drop_amount"),
            "price_drop_amount",
            None,
        ),
    )


def _application_document(
    document: Mapping[str, object],
    lidl: dict[str, object],
    state_file: str,
) -> dict[str, object]:
    price_drop: dict[str, object] = {}
    if "price_drop_percentage" in document:
        price_drop["percentage"] = document["price_drop_percentage"]
    if "price_drop_amount" in document:
        price_drop["fixed_amount"] = document["price_drop_amount"]
    application_document: dict[str, object] = {
        "schema_version": 1,
        "provider": {"lidl": lidl},
        "state": {"file": state_file},
        "scheduler": {"interval_seconds": document["interval_seconds"]},
    }
    if price_drop:
        application_document["rules"] = {"price_drop": price_drop}
    return application_document


def _parse_daily_digest(
    document: Mapping[str, object],
    catalog: CatalogMonitoringConfig | None,
) -> DailyDigestConfig | None:
    enabled = document.get("daily_digest_enabled", False)
    if not isinstance(enabled, bool):
        raise TypeError("daily_digest_enabled must be a boolean")
    if not enabled:
        if "daily_digest_time" in document:
            raise ValueError("daily_digest_time requires daily_digest_enabled")
        return None
    percentage = cast(CatalogMonitoringConfig, catalog).price_drop_percentage
    if percentage is None:
        raise ValueError("daily digest requires price_drop_percentage")
    value = document.get("daily_digest_time", "08:00")
    if not isinstance(value, str):
        raise TypeError("daily_digest_time must be a string")
    if _TIME_PATTERN.fullmatch(value) is None:
        raise ValueError("daily_digest_time must use HH:MM")
    hour, minute = (int(part) for part in value.split(":"))
    return DailyDigestConfig(time(hour, minute), Percentage(percentage))


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _optional_decimal(
    value: object,
    name: str,
    maximum: Decimal | None,
) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a decimal string") from error
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    if parsed < Decimal("0") or (maximum is not None and parsed > maximum):
        raise ValueError(f"{name} is outside its allowed range")
    return parsed


def _validate_keys(document: Mapping[object, object]) -> None:
    if not all(isinstance(key, str) for key in document):
        raise ConfigurationError("Home Assistant option keys must be strings")
    keys = cast(set[str], set(document))
    unknown = keys - _ALLOWED_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationError(f"Home Assistant options contain unknown keys: {names}")
    required = _REQUIRED_KEYS
    if document.get("catalog_enabled") is not True:
        required = required | {"product_urls"}
    missing = required - keys
    if missing:
        names = ", ".join(sorted(missing))
        raise ConfigurationError(f"Home Assistant options are missing keys: {names}")
