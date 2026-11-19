"""Native App options remain pure, strict and safe for older configurations."""

from dataclasses import replace
from pathlib import Path

import pytest

from applications.homeassistant import parse_homeassistant_options
from applications.homeassistant.composition import _compose_homeassistant
from core.configuration import ConfigurationError
from tests.unit.homeassistant_app.helpers import create_options, create_config, TIMESTAMP
from tests.unit.providers.test_watch_preferences import URL
from uuid import uuid4


def options(**extra):
    values = create_options()
    values.update(catalog_enabled=True, product_urls=[])
    values.update(extra)
    return values


def test_personal_options_resolve_and_compose_without_io() -> None:
    config = parse_homeassistant_options(options(
        favorite_product_urls=[URL], target_prices=[{"url": URL, "amount": "80.00"}],
        included_categories=["zahrada"], hidden_product_urls=[],
    ), Path("/data"))
    assert config.personal_watch.targets[0][1].amount == 80
    assert config.personal_watch.source().seed_references()
    result = _compose_homeassistant(config, "token", lambda: TIMESTAMP, uuid4)
    assert result.catalog_workflow._seed_references[0].external_id == "p100123"


def test_safe_empty_defaults_preserve_explicit_and_catalog_modes() -> None:
    assert parse_homeassistant_options(options(), Path("/data")).personal_watch is None
    original = create_options()
    original.update(favorite_product_urls=[], hidden_product_urls=[], target_prices=[], included_categories=[])
    assert parse_homeassistant_options(original, Path("/data")).personal_watch is None
    original["favorite_product_urls"] = [URL]
    with pytest.raises(ConfigurationError, match="catalog"):
        parse_homeassistant_options(original, Path("/data"))


@pytest.mark.parametrize("extra", [
    {"favorite_product_urls": "url"}, {"hidden_product_urls": [1]},
    {"target_prices": {}}, {"target_prices": [{}]},
    {"target_prices": [{"url": URL, "amount": "80", "unknown": 1}]},
    {"target_prices": [{"url": URL, "amount": 80}]},
    {"target_prices": [{"url": URL, "amount": "invalid"}]},
    {"target_prices": [{"url": URL, "amount": "NaN"}]},
    {"target_prices": [{"url": URL, "amount": "-1"}]},
    {"target_prices": [{"url": URL, "amount": "80", "currency": "XXX"}]},
    {"target_prices": [{"url": URL, "amount": "80", "currency": "USD"}]},
    {"watch_category_rules": [{"name": "custom"}]},
    {"watch_category_rules": [{"name": "custom", "keywords": []}]},
    {"watch_category_rules": [{"name": "custom", "keywords": ["phrase"], "extra": 1}]},
    {"included_categories": ["undefined"]},
])
def test_malformed_personal_options_are_configuration_errors(extra) -> None:
    with pytest.raises(ConfigurationError):
        parse_homeassistant_options(options(**extra), Path("/data"))


def test_custom_category_rules_and_config_type_validation() -> None:
    config = parse_homeassistant_options(options(watch_category_rules=[{"name": "moje", "keywords": ["sada bitů"]}], included_categories=["moje"]), Path("/data"))
    assert config.personal_watch.included == ("moje",)
    with pytest.raises(TypeError):
        replace(config, personal_watch=object())
