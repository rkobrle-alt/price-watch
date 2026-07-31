"""Tests for pure versioned configuration parsing."""

import importlib
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from applications.configuration import ApplicationConfig, parse_configuration
from core.configuration import ConfigurationError

parser_module = importlib.import_module("applications.configuration.parser")


def _document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "provider": {
            "lidl": {
                "product_urls": ["https://www.lidl.cz/tool/p100"],
                "timeout_seconds": 15,
            }
        },
        "state": {"file": "data/state.json"},
        "rules": {
            "price_drop": {
                "percentage": "10.50",
                "fixed_amount": "250.00",
            }
        },
        "scheduler": {"interval_seconds": 300},
    }


def test_complete_document_preserves_values_and_relative_path() -> None:
    config = parse_configuration(_document(), Path("configuration"))

    assert config == ApplicationConfig(
        product_urls=("https://www.lidl.cz/tool/p100",),
        state_file=Path("configuration/data/state.json"),
        timeout_seconds=15,
        price_drop_percentage=Decimal("10.50"),
        price_drop_amount=Decimal("250.00"),
        interval=timedelta(seconds=300),
    )
    assert config.price_drop_amount.as_tuple().exponent == -2


def test_minimal_document_uses_defaults() -> None:
    document = _document()
    cast(dict[str, object], cast(dict[str, object], document["provider"])["lidl"]).pop(
        "timeout_seconds"
    )
    document.pop("rules")
    document.pop("scheduler")

    config = parse_configuration(document, Path("."))

    assert config.timeout_seconds == 10
    assert config.price_drop_percentage is None
    assert config.price_drop_amount is None
    assert config.interval is None


def test_empty_rules_and_missing_price_drop_use_no_thresholds() -> None:
    document = _document()
    document["rules"] = {}
    empty_rules = parse_configuration(document, Path("."))
    document["rules"] = {"price_drop": {}}
    empty_price_drop = parse_configuration(document, Path("."))

    assert empty_rules.price_drop_percentage is None
    assert empty_price_drop.price_drop_amount is None


def test_absolute_state_path_is_preserved(tmp_path: Path) -> None:
    document = _document()
    state_path = tmp_path / "state.json"
    document["state"] = {"file": str(state_path)}

    config = parse_configuration(document, Path("ignored"))

    assert config.state_file == state_path


@pytest.mark.parametrize(
    ("document", "base_directory"),
    [
        (cast(Mapping[str, object], []), Path(".")),
        (_document(), cast(Path, ".")),
    ],
)
def test_parser_rejects_invalid_public_argument_types(
    document: Mapping[str, object],
    base_directory: Path,
) -> None:
    with pytest.raises(TypeError):
        parse_configuration(document, base_directory)


def _invalid_documents() -> list[tuple[dict[object, object], str]]:
    cases: list[tuple[dict[object, object], str]] = []

    def add(mutator: object, expected: str) -> None:
        document = _document()
        cast(object, mutator)(document)
        cases.append((cast(dict[object, object], document), expected))

    add(lambda value: value.update({1: "invalid"}), "keys must be strings")
    add(lambda value: value.update({"unknown": 1}), "unknown keys")
    add(lambda value: value.pop("state"), "missing required keys")
    add(lambda value: value.update(schema_version=True), "integer 1")
    add(lambda value: value.update(schema_version="1"), "integer 1")
    add(lambda value: value.update(schema_version=2), "unsupported")
    add(lambda value: value.update(provider=[]), "provider must be a table")
    add(lambda value: value.update(provider={}), "provider is missing")
    add(lambda value: value.update(provider={"other": {}}), "unknown keys")
    add(lambda value: value.update(provider={"lidl": []}), "provider.lidl must")
    add(
        lambda value: cast(dict[str, object], cast(dict[str, object], value["provider"])["lidl"]).update(unknown=1),
        "unknown keys",
    )
    add(
        lambda value: cast(dict[str, object], cast(dict[str, object], value["provider"])["lidl"]).pop("product_urls"),
        "missing required keys",
    )
    add(lambda value: value.update(state=[]), "state must be a table")
    add(lambda value: value.update(state={}), "state is missing")
    add(lambda value: value.update(state={"file": "x", "bad": 1}), "unknown keys")
    add(
        lambda value: cast(dict[str, object], cast(dict[str, object], value["provider"])["lidl"]).update(product_urls="url"),
        "array of strings",
    )
    add(
        lambda value: cast(dict[str, object], cast(dict[str, object], value["provider"])["lidl"]).update(product_urls=[1]),
        "array of strings",
    )
    add(
        lambda value: cast(dict[str, object], cast(dict[str, object], value["provider"])["lidl"]).update(product_urls=[]),
        "cannot be empty",
    )
    add(
        lambda value: cast(dict[str, object], cast(dict[str, object], value["provider"])["lidl"]).update(product_urls=[" "]),
        "blank values",
    )
    add(
        lambda value: cast(dict[str, object], cast(dict[str, object], value["provider"])["lidl"]).update(timeout_seconds=True),
        "positive integer",
    )
    add(
        lambda value: cast(dict[str, object], cast(dict[str, object], value["provider"])["lidl"]).update(timeout_seconds=0),
        "must be positive",
    )
    add(lambda value: value.update(state={"file": 1}), "must be a string")
    add(lambda value: value.update(state={"file": " "}), "cannot be blank")
    add(lambda value: value.update(rules=[]), "rules must be a table")
    add(lambda value: value.update(rules={"bad": {}}), "unknown keys")
    add(lambda value: value.update(rules={"price_drop": []}), "price_drop must")
    add(
        lambda value: value.update(rules={"price_drop": {"bad": 1}}),
        "unknown keys",
    )
    add(
        lambda value: value.update(rules={"price_drop": {"percentage": 10.0}}),
        "decimal string",
    )
    add(
        lambda value: value.update(rules={"price_drop": {"percentage": "bad"}}),
        "decimal string",
    )
    add(
        lambda value: value.update(rules={"price_drop": {"percentage": "NaN"}}),
        "must be finite",
    )
    add(
        lambda value: value.update(rules={"price_drop": {"percentage": "101"}}),
        "allowed range",
    )
    add(
        lambda value: value.update(rules={"price_drop": {"fixed_amount": "-1"}}),
        "allowed range",
    )
    add(lambda value: value.update(scheduler=[]), "scheduler must be a table")
    add(lambda value: value.update(scheduler={}), "missing required keys")
    add(
        lambda value: value.update(scheduler={"interval_seconds": 1, "bad": 2}),
        "unknown keys",
    )
    add(
        lambda value: value.update(scheduler={"interval_seconds": "1"}),
        "positive integer",
    )
    add(
        lambda value: value.update(scheduler={"interval_seconds": -1}),
        "must be positive",
    )
    return cases


@pytest.mark.parametrize(("document", "expected"), _invalid_documents())
def test_parser_rejects_invalid_document(
    document: dict[object, object],
    expected: str,
) -> None:
    with pytest.raises(ConfigurationError, match=expected):
        parse_configuration(cast(Mapping[str, object], document), Path("."))


@pytest.mark.parametrize("failure", [TypeError("bad model"), ValueError("bad model")])
def test_parser_translates_model_invariant_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    def fail(**values: object) -> ApplicationConfig:
        raise failure

    monkeypatch.setattr(parser_module, "ApplicationConfig", fail)

    with pytest.raises(ConfigurationError) as captured:
        parse_configuration(_document(), Path("."))

    assert captured.value.__cause__ is failure
