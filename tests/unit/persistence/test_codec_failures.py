"""Validation tests for schema-v1 persisted snapshot data."""

from copy import deepcopy
from pathlib import Path

import pytest

from core.state import StateStoreError
from infrastructure.persistence.json import JsonStateStore
from infrastructure.persistence.json.codec import (
    SnapshotCodecError,
    decode_snapshot,
    validate_document,
)
from tests.unit.persistence.helpers import (
    OTHER_PRODUCT_ID,
    PRODUCT_ID,
    create_document_with,
    create_snapshot,
    write_json,
)


def _product(document: dict[str, object]) -> dict[str, object]:
    snapshots = document["snapshots"]
    assert isinstance(snapshots, dict)
    snapshot = snapshots[str(PRODUCT_ID.value)]
    assert isinstance(snapshot, dict)
    product = snapshot["product"]
    assert isinstance(product, dict)
    return product


def _snapshot(document: dict[str, object]) -> dict[str, object]:
    snapshots = document["snapshots"]
    assert isinstance(snapshots, dict)
    snapshot = snapshots[str(PRODUCT_ID.value)]
    assert isinstance(snapshot, dict)
    return snapshot


def _assert_store_rejects(tmp_path: Path, document: object) -> StateStoreError:
    destination = tmp_path / "state.json"
    write_json(destination, document)
    with pytest.raises(StateStoreError) as captured:
        JsonStateStore(destination).load(PRODUCT_ID)
    assert isinstance(captured.value.__cause__, SnapshotCodecError)
    return captured.value


@pytest.mark.parametrize(
    "document",
    [
        [],
        {},
        {"schema_version": True, "snapshots": {}},
        {"schema_version": "1", "snapshots": {}},
        {"schema_version": 2, "snapshots": {}},
        {"schema_version": 1},
        {"schema_version": 1, "snapshots": []},
        {"schema_version": 1, "snapshots": {"not-a-uuid": {}}},
        {
            "schema_version": 1,
            "snapshots": {str(PRODUCT_ID.value).upper(): {}},
        },
        {
            "schema_version": 1,
            "snapshots": {str(PRODUCT_ID.value): None},
        },
    ],
)
def test_store_rejects_invalid_document_structure(
    tmp_path: Path,
    document: object,
) -> None:
    _assert_store_rejects(tmp_path, document)


def test_document_validator_rejects_non_string_object_keys() -> None:
    with pytest.raises(SnapshotCodecError, match="object"):
        validate_document({"schema_version": 1, "snapshots": {1: {}}})


def test_decoder_rejects_invalid_storage_key_directly() -> None:
    document = create_document_with(create_snapshot())
    stored = _snapshot(document)

    with pytest.raises(SnapshotCodecError, match="UUID"):
        decode_snapshot(stored, "invalid")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "invalid"),
        ("id", str(PRODUCT_ID.value).upper()),
        ("provider_id", "invalid"),
        ("brand", 1),
        ("name", " "),
        ("current_price", []),
        ("discount_percent", "invalid"),
        ("discount_percent", "101"),
        ("url", 1),
        ("image_url", 1),
        ("created_at", "invalid"),
        ("created_at", "2026-07-31T10:00:00"),
        ("availability", 1),
    ],
)
def test_store_rejects_invalid_product_fields(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    document = create_document_with(create_snapshot())
    _product(document)[field] = value

    _assert_store_rejects(tmp_path, document)


def test_store_rejects_missing_required_product_field(tmp_path: Path) -> None:
    document = create_document_with(create_snapshot())
    del _product(document)["brand"]

    _assert_store_rejects(tmp_path, document)


@pytest.mark.parametrize(
    ("price_name", "field", "value"),
    [
        ("current_price", "amount", 1),
        ("current_price", "amount", "invalid"),
        ("current_price", "amount", "-1"),
        ("current_price", "currency", 1),
        ("current_price", "currency", "GBP"),
        ("original_price", "currency", "USD"),
    ],
)
def test_store_rejects_invalid_money_fields(
    tmp_path: Path,
    price_name: str,
    field: str,
    value: object,
) -> None:
    document = create_document_with(create_snapshot())
    money = _product(document)[price_name]
    assert isinstance(money, dict)
    money[field] = value

    _assert_store_rejects(tmp_path, document)


def test_store_rejects_invalid_original_price_shape(tmp_path: Path) -> None:
    document = create_document_with(create_snapshot())
    _product(document)["original_price"] = "invalid"

    _assert_store_rejects(tmp_path, document)


@pytest.mark.parametrize("timestamp", [1, "invalid", "2026-07-31T10:00:00"])
def test_store_rejects_invalid_snapshot_timestamp(
    tmp_path: Path,
    timestamp: object,
) -> None:
    document = create_document_with(create_snapshot())
    _snapshot(document)["timestamp"] = timestamp

    _assert_store_rejects(tmp_path, document)


def test_store_rejects_storage_key_product_id_mismatch(tmp_path: Path) -> None:
    document = create_document_with(create_snapshot())
    snapshots = document["snapshots"]
    assert isinstance(snapshots, dict)
    stored = snapshots.pop(str(PRODUCT_ID.value))
    snapshots[str(OTHER_PRODUCT_ID.value)] = stored

    destination = tmp_path / "state.json"
    write_json(destination, document)
    with pytest.raises(StateStoreError, match="decode") as captured:
        JsonStateStore(destination).load(OTHER_PRODUCT_ID)

    assert isinstance(captured.value.__cause__, SnapshotCodecError)


def test_unknown_additional_fields_are_ignored(tmp_path: Path) -> None:
    snapshot = create_snapshot()
    document = create_document_with(snapshot)
    document["future"] = "value"
    _product(document)["future"] = {"nested": True}
    destination = tmp_path / "state.json"
    write_json(destination, document)

    assert JsonStateStore(destination).load(PRODUCT_ID) == snapshot


def test_store_rejects_nan_percentage_through_domain_validation(tmp_path: Path) -> None:
    document = deepcopy(create_document_with(create_snapshot()))
    _product(document)["discount_percent"] = "NaN"

    _assert_store_rejects(tmp_path, document)
