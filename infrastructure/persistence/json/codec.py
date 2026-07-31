"""Internal schema-v1 codec for immutable product state snapshots."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from core.domain import (
    Currency,
    Money,
    Percentage,
    Product,
    ProductId,
    ProviderId,
    ValidationError,
)
from core.state import StateSnapshot

SCHEMA_VERSION = 1


class SnapshotCodecError(ValueError):
    """Report an invalid JSON snapshot document representation."""


def create_document() -> dict[str, object]:
    """Create an empty schema-v1 document."""
    return {"schema_version": SCHEMA_VERSION, "snapshots": {}}


def validate_document(value: object) -> dict[str, object]:
    """Validate and return a schema-v1 document object."""
    document = _object(value, "document")
    version = _field(document, "schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise SnapshotCodecError("schema_version must be an integer")
    if version != SCHEMA_VERSION:
        raise SnapshotCodecError(f"unsupported schema_version: {version}")

    snapshots = _object(_field(document, "snapshots"), "snapshots")
    for storage_key, snapshot in snapshots.items():
        _uuid(storage_key, "snapshot storage key")
        _object(snapshot, f"snapshot {storage_key}")
    return document


def snapshot_entries(document: dict[str, object]) -> dict[str, object]:
    """Return the already validated snapshot entry mapping."""
    return _object(document["snapshots"], "snapshots")


def encode_snapshot(snapshot: StateSnapshot) -> dict[str, object]:
    """Encode a validated snapshot using schema version 1."""
    product = snapshot.product
    return {
        "product": {
            "availability": product.availability,
            "brand": product.brand,
            "created_at": product.created_at.isoformat(),
            "current_price": _encode_money(product.current_price),
            "discount_percent": str(product.discount_percent.value),
            "id": str(product.id.value),
            "image_url": product.image_url,
            "name": product.name,
            "original_price": (
                None
                if product.original_price is None
                else _encode_money(product.original_price)
            ),
            "provider_id": str(product.provider_id.value),
            "url": product.url,
        },
        "timestamp": snapshot.timestamp.isoformat(),
    }


def decode_snapshot(value: object, storage_key: str) -> StateSnapshot:
    """Decode one persisted snapshot and enforce its storage identity."""
    _uuid(storage_key, "snapshot storage key")
    snapshot_data = _object(value, "snapshot")
    product_data = _object(_field(snapshot_data, "product"), "product")

    try:
        product = Product(
            id=ProductId(_uuid(_field(product_data, "id"), "product.id")),
            provider_id=ProviderId(
                _uuid(_field(product_data, "provider_id"), "product.provider_id")
            ),
            brand=_string(_field(product_data, "brand"), "product.brand"),
            name=_string(_field(product_data, "name"), "product.name"),
            current_price=_decode_money(
                _field(product_data, "current_price"),
                "product.current_price",
            ),
            original_price=_decode_optional_money(
                _field(product_data, "original_price")
            ),
            discount_percent=Percentage(
                _decimal(
                    _field(product_data, "discount_percent"),
                    "product.discount_percent",
                )
            ),
            url=_string(_field(product_data, "url"), "product.url"),
            image_url=_optional_string(
                _field(product_data, "image_url"),
                "product.image_url",
            ),
            created_at=_datetime(
                _field(product_data, "created_at"),
                "product.created_at",
            ),
            availability=_boolean(
                _field(product_data, "availability"),
                "product.availability",
            ),
        )
        snapshot = StateSnapshot(
            product=product,
            timestamp=_datetime(_field(snapshot_data, "timestamp"), "timestamp"),
        )
    except SnapshotCodecError:
        raise
    except (TypeError, ValueError, ValidationError) as error:
        raise SnapshotCodecError("persisted snapshot violates invariants") from error

    if str(snapshot.product.id.value) != storage_key:
        raise SnapshotCodecError("snapshot storage key does not match product id")
    return snapshot


def _encode_money(money: Money) -> dict[str, str]:
    return {"amount": str(money.amount), "currency": money.currency.value}


def _decode_money(value: object, field_name: str) -> Money:
    money = _object(value, field_name)
    currency_text = _string(_field(money, "currency"), f"{field_name}.currency")
    try:
        currency = Currency(currency_text)
    except ValueError as error:
        raise SnapshotCodecError(
            f"{field_name}.currency is unsupported"
        ) from error
    return Money(
        _decimal(_field(money, "amount"), f"{field_name}.amount"),
        currency,
    )


def _decode_optional_money(value: object) -> Money | None:
    if value is None:
        return None
    return _decode_money(value, "product.original_price")


def _object(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise SnapshotCodecError(f"{field_name} must be an object")
    return value


def _field(value: dict[str, object], name: str) -> object:
    if name not in value:
        raise SnapshotCodecError(f"missing required field: {name}")
    return value[name]


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise SnapshotCodecError(f"{field_name} must be a string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise SnapshotCodecError(f"{field_name} must be a boolean")
    return value


def _uuid(value: object, field_name: str) -> UUID:
    text = _string(value, field_name)
    try:
        identifier = UUID(text)
    except ValueError as error:
        raise SnapshotCodecError(f"{field_name} must be a UUID") from error
    if str(identifier) != text:
        raise SnapshotCodecError(f"{field_name} must be a canonical UUID")
    return identifier


def _decimal(value: object, field_name: str) -> Decimal:
    text = _string(value, field_name)
    try:
        return Decimal(text)
    except InvalidOperation as error:
        raise SnapshotCodecError(f"{field_name} must be a Decimal") from error


def _datetime(value: object, field_name: str) -> datetime:
    text = _string(value, field_name)
    try:
        return datetime.fromisoformat(text)
    except ValueError as error:
        raise SnapshotCodecError(f"{field_name} must be an ISO datetime") from error
