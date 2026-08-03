"""Internal schema-v1 JSON document codec for product snapshots."""

from uuid import UUID

from infrastructure.persistence.snapshot_codec import (
    SnapshotCodecError,
    decode_snapshot,
    encode_snapshot,
)

SCHEMA_VERSION = 1


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


def _uuid(text: str, field_name: str) -> UUID:
    try:
        identifier = UUID(text)
    except ValueError as error:
        raise SnapshotCodecError(f"{field_name} must be a UUID") from error
    if str(identifier) != text:
        raise SnapshotCodecError(f"{field_name} must be a canonical UUID")
    return identifier