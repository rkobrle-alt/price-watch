"""Tests for Home Assistant catalog-mode option configuration."""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from applications.catalog_monitoring import CatalogMonitoringConfig
from applications.homeassistant import HomeAssistantConfig, parse_homeassistant_options
from core.configuration import ConfigurationError

_BASE_OPTIONS: dict[str, object] = {
    "catalog_enabled": True,
    "notify_entity": "notify.gmail_parkside",
    "interval_seconds": 300,
}


def _options(**overrides: object) -> dict[str, object]:
    options = dict(_BASE_OPTIONS)
    options.update(overrides)
    return options


def test_catalog_options_use_documented_defaults_without_product_urls() -> None:
    result = parse_homeassistant_options(_options(), Path("/data"))

    assert result.application is None
    assert result.catalog == CatalogMonitoringConfig(
        database_file=Path("/data/catalog.sqlite3"),
        interval=timedelta(seconds=300),
    )
    assert result.notify_entity == "notify.gmail_parkside"
    assert result.notification_title == "Price Watch"


def test_catalog_options_preserve_exact_custom_values() -> None:
    result = parse_homeassistant_options(
        _options(
            product_urls=[],
            timeout_seconds=17,
            catalog_batch_size=40,
            catalog_discovery_interval_cycles=12,
            price_drop_percentage="20.00",
            price_drop_amount="250.00",
            notification_title="Parkside Catalog",
        ),
        Path("data"),
    )

    catalog = result.catalog
    assert catalog is not None
    assert catalog.database_file == Path("data/catalog.sqlite3")
    assert catalog.timeout_seconds == 17
    assert catalog.batch_size == 40
    assert catalog.discovery_interval_cycles == 12
    assert catalog.price_drop_percentage == Decimal("20.00")
    assert catalog.price_drop_amount == Decimal("250.00")
    assert result.notification_title == "Parkside Catalog"


def test_homeassistant_config_accepts_exactly_catalog_mode() -> None:
    catalog = CatalogMonitoringConfig(
        Path("catalog.sqlite3"),
        timedelta(minutes=5),
    )

    result = HomeAssistantConfig(
        application=None,
        catalog=catalog,
        notify_entity="notify.gmail_parkside",
    )

    assert result.catalog is catalog


@pytest.mark.parametrize(
    ("application", "catalog", "exception_type", "message"),
    [
        (None, None, ValueError, "exactly one"),
        (object(), None, TypeError, "application"),
        (None, object(), TypeError, "catalog"),
    ],
)
def test_homeassistant_config_rejects_invalid_mode_members(
    application: object,
    catalog: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        HomeAssistantConfig(
            application=application,  # type: ignore[arg-type]
            catalog=catalog,  # type: ignore[arg-type]
            notify_entity="notify.gmail_parkside",
        )


def test_homeassistant_config_rejects_both_modes() -> None:
    explicit = parse_homeassistant_options(
        {
            "product_urls": ["https://www.lidl.cz/p/parkside-tool/p100"],
            "notify_entity": "notify.gmail_parkside",
            "interval_seconds": 300,
        },
        Path("/data"),
    ).application
    catalog = CatalogMonitoringConfig(
        Path("catalog.sqlite3"),
        timedelta(minutes=5),
    )

    with pytest.raises(ValueError, match="exactly one"):
        HomeAssistantConfig(
            explicit,
            "notify.gmail_parkside",
            catalog=catalog,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"catalog_enabled": "yes"}, "catalog_enabled"),
        ({"product_urls": ["https://www.lidl.cz/p/parkside-tool/p100"]}, "product_urls"),
        ({"catalog_batch_size": True}, "catalog_batch_size"),
        ({"catalog_batch_size": 0}, "catalog_batch_size"),
        ({"catalog_discovery_interval_cycles": "12"}, "catalog_discovery_interval_cycles"),
        ({"catalog_discovery_interval_cycles": -1}, "catalog_discovery_interval_cycles"),
        ({"timeout_seconds": 1.5}, "timeout_seconds"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"interval_seconds": True}, "interval_seconds"),
        ({"interval_seconds": 0}, "interval_seconds"),
        ({"price_drop_percentage": 20}, "price_drop_percentage"),
        ({"price_drop_percentage": "bad"}, "price_drop_percentage"),
        ({"price_drop_percentage": "101"}, "price_drop_percentage"),
        ({"price_drop_amount": 20}, "price_drop_amount"),
        ({"price_drop_amount": "NaN"}, "price_drop_amount"),
        ({"price_drop_amount": "-1"}, "price_drop_amount"),
    ],
)
def test_catalog_parser_rejects_invalid_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_homeassistant_options(_options(**overrides), Path("/data"))


@pytest.mark.parametrize(
    "key",
    ["catalog_batch_size", "catalog_discovery_interval_cycles"],
)
def test_explicit_mode_rejects_catalog_only_options(key: str) -> None:
    options = {
        "product_urls": ["https://www.lidl.cz/p/parkside-tool/p100"],
        "notify_entity": "notify.gmail_parkside",
        "interval_seconds": 300,
        key: 2,
    }

    with pytest.raises(ConfigurationError, match="require catalog_enabled"):
        parse_homeassistant_options(options, Path("/data"))
