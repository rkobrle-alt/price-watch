"""Tests for concrete Home Assistant synchronization composition."""

from dataclasses import replace
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest

from applications.cli.composition import (
    BACK_IN_STOCK_RULE_ID,
    PRICE_DROP_RULE_ID,
)
from applications.homeassistant.composition import _compose_homeassistant
from applications.version import VERSION
from core.domain import RuleType
from infrastructure.homeassistant import UrllibHomeAssistantClient
from infrastructure.http import UrllibTextHttpClient
from infrastructure.notifications.homeassistant import (
    HomeAssistantNotificationChannel,
)
from infrastructure.persistence.json import JsonStateStore
from infrastructure.providers.lidl import LidlParksideProvider
from tests.unit.homeassistant_app.helpers import TIMESTAMP, create_config


def test_composition_assembles_exact_supervisor_stack() -> None:
    config = create_config(
        percentage=Decimal("12.50"),
        amount=Decimal("250.00"),
    )

    result = _compose_homeassistant(config, "injected-token", lambda: TIMESTAMP, uuid4)

    assert result.interval == config.application.interval
    assert tuple(rule.id for rule in result.rules) == (
        PRICE_DROP_RULE_ID,
        BACK_IN_STOCK_RULE_ID,
    )
    assert tuple(rule.rule_type for rule in result.rules) == (
        RuleType.PRICE_DROP,
        RuleType.BACK_IN_STOCK,
    )
    assert dict(result.rules[0].parameters) == {
        "percentage": Decimal("12.50"),
        "fixed_amount": Decimal("250.00"),
    }
    assert result.rules[0].name == "Price Watch price drop"
    assert result.rules[1].name == "Price Watch back in stock"

    workflow = result.workflow
    provider = workflow._providers[0]
    assert isinstance(provider, LidlParksideProvider)
    assert isinstance(provider._http_client, UrllibTextHttpClient)
    assert provider._http_client._timeout_seconds == 12
    assert provider._http_client._user_agent == f"PriceWatch/{VERSION}"
    assert isinstance(workflow._state_store, JsonStateStore)
    assert workflow._state_store._path == config.application.state_file
    channel = workflow._notification_channel
    assert isinstance(channel, HomeAssistantNotificationChannel)
    assert channel._entity_id == "notify.gmail_parkside"
    assert channel._title == "Parkside Price Watch"
    client = channel._client
    assert isinstance(client, UrllibHomeAssistantClient)
    assert client._base_url == "http://supervisor/core/api"
    assert client._access_token == "injected-token"
    assert client._timeout_seconds == 12
    assert client._user_agent == f"PriceWatch/{VERSION}"


def test_composition_supports_rules_without_thresholds() -> None:
    result = _compose_homeassistant(
        create_config(percentage=None, amount=None),
        "token",
        lambda: TIMESTAMP,
        uuid4,
    )

    assert dict(result.rules[0].parameters) == {}


@pytest.mark.parametrize(
    ("config", "token", "clock", "factory", "exception_type", "message"),
    [
        (object(), "token", lambda: TIMESTAMP, uuid4, TypeError, "config"),
        (create_config(), 1, lambda: TIMESTAMP, uuid4, TypeError, "access_token"),
        (create_config(), " ", lambda: TIMESTAMP, uuid4, ValueError, "access_token"),
        (create_config(), "token", object(), uuid4, TypeError, "clock"),
        (
            create_config(),
            "token",
            lambda: TIMESTAMP,
            object(),
            TypeError,
            "notification_id_factory",
        ),
    ],
)
def test_composition_rejects_invalid_dependencies(
    config: object,
    token: object,
    clock: object,
    factory: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        _compose_homeassistant(
            cast(object, config),
            cast(str, token),
            cast(object, clock),
            cast(object, factory),
        )


def test_composition_defends_against_missing_interval_after_validation() -> None:
    config = create_config()
    object.__setattr__(config, "application", replace(config.application, interval=None))

    with pytest.raises(ValueError, match="interval"):
        _compose_homeassistant(config, "token", lambda: TIMESTAMP, uuid4)
