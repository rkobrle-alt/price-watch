"""Public API tests for JSON persistence."""

import inspect

from core.state import StateSnapshot
import infrastructure.persistence.json as json_api
from infrastructure.persistence.json import JsonStateStore


def test_json_persistence_public_api_is_explicit() -> None:
    assert json_api.__all__ == ["JsonStateStore"]
    assert json_api.JsonStateStore is JsonStateStore


def test_public_class_and_methods_are_documented_and_typed() -> None:
    assert inspect.getdoc(JsonStateStore)
    assert inspect.getdoc(JsonStateStore.__init__)
    assert inspect.getdoc(JsonStateStore.load)
    assert inspect.getdoc(JsonStateStore.save)
    assert inspect.signature(JsonStateStore.__init__).return_annotation is None
    assert inspect.signature(JsonStateStore.load).return_annotation == (
        StateSnapshot | None
    )
    assert inspect.signature(JsonStateStore.save).return_annotation is None
