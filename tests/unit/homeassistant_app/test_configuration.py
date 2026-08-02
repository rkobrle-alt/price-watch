"""Tests for pure Home Assistant App option configuration."""

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from applications.homeassistant import (
    HomeAssistantConfig,
    parse_homeassistant_options,
)
from core.configuration import ConfigurationError
from tests.unit.homeassistant_app.helpers import (
    PRODUCT_URL,
    create_config,
    create_options,
)


def test_parse_complete_options_preserves_exact_values() -> None:
    result = parse_homeassistant_options(
        create_options(
            timeout_seconds=17,
            price_drop_percentage="12.50",
            price_drop_amount="250.00",
            notification_title="Lidl Parkside",
        ),
        Path("/data"),
    )

    assert result.application.product_urls == (PRODUCT_URL,)
    assert result.application.state_file == Path("/data/state.json")
    assert result.application.timeout_seconds == 17
    assert result.application.price_drop_percentage == Decimal("12.50")
    assert result.application.price_drop_amount == Decimal("250.00")
    assert result.application.interval == timedelta(seconds=300)
    assert result.notify_entity == "notify.gmail_parkside"
    assert result.notification_title == "Lidl Parkside"


def test_parse_options_uses_optional_defaults() -> None:
    result = parse_homeassistant_options(create_options(), Path("data"))

    assert result.application.timeout_seconds == 10
    assert result.application.price_drop_percentage is None
    assert result.application.price_drop_amount is None
    assert result.application.state_file == Path("data/state.json")
    assert result.notification_title == "Price Watch"


def test_config_is_frozen_and_slotted() -> None:
    config = create_config()

    with pytest.raises(FrozenInstanceError):
        config.notify_entity = "notify.other"  # type: ignore[misc]
    assert not hasattr(config, "__dict__")


@pytest.mark.parametrize(
    ("field", "value", "exception_type", "message"),
    [
        ("application", object(), TypeError, "application"),
        ("notify_entity", 1, TypeError, "notify_entity"),
        ("notify_entity", "sensor.mail", ValueError, "notify_entity"),
        ("notify_entity", "notify.Gmail", ValueError, "notify_entity"),
        ("notification_title", 1, TypeError, "notification_title"),
        ("notification_title", " ", ValueError, "notification_title"),
    ],
)
def test_config_rejects_invalid_members(
    field: str,
    value: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "application": create_config().application,
        "notify_entity": "notify.gmail_parkside",
        "notification_title": "Price Watch",
    }
    values[field] = value

    with pytest.raises(exception_type, match=message):
        HomeAssistantConfig(**values)


def test_config_requires_application_interval() -> None:
    application = replace(create_config().application, interval=None)

    with pytest.raises(ValueError, match="interval"):
        HomeAssistantConfig(application, "notify.gmail_parkside")


@pytest.mark.parametrize(
    ("document", "directory", "message"),
    [
        ([], Path("/data"), "document"),
        (create_options(), "data", "data_directory"),
    ],
)
def test_parser_rejects_invalid_public_argument_types(
    document: object,
    directory: object,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        parse_homeassistant_options(
            cast(dict[str, object], document),
            cast(Path, directory),
        )


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({1: "bad"}, "keys must be strings"),
        (create_options(extra=True), "unknown keys: extra"),
        ({}, "interval_seconds, notify_entity, product_urls"),
        (
            {"product_urls": [PRODUCT_URL], "interval_seconds": 300},
            "notify_entity",
        ),
    ],
)
def test_parser_rejects_invalid_key_sets(
    document: dict[object, object],
    message: str,
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_homeassistant_options(
            cast(dict[str, object], document),
            Path("/data"),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"product_urls": []}, "product_urls"),
        ({"product_urls": PRODUCT_URL}, "product_urls"),
        ({"product_urls": [" "]}, "product_urls"),
        ({"interval_seconds": True}, "interval_seconds"),
        ({"interval_seconds": 0}, "interval_seconds"),
        ({"timeout_seconds": "10"}, "timeout_seconds"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"price_drop_percentage": 10.0}, "percentage"),
        ({"price_drop_percentage": "invalid"}, "percentage"),
        ({"price_drop_percentage": "101"}, "percentage"),
        ({"price_drop_amount": 10}, "fixed_amount"),
        ({"price_drop_amount": "-1"}, "fixed_amount"),
        ({"notify_entity": 1}, "notify_entity"),
        ({"notify_entity": "notify.bad-name"}, "notify_entity"),
        ({"notification_title": 1}, "notification_title"),
        ({"notification_title": " "}, "notification_title"),
    ],
)
def test_parser_rejects_invalid_option_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_homeassistant_options(create_options(**overrides), Path("/data"))
