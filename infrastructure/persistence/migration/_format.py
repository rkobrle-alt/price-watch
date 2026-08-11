"""Encode and validate the versioned migration ZIP format."""

import json
import zipfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from infrastructure.persistence.migration._state import (
    SCHEMA_VERSION,
    sha256,
    validate_state_bytes,
)
from infrastructure.persistence.migration.model import (
    MigrationArchiveError,
    STATE_FILE_NAMES,
)

MANIFEST_FILE_NAME = "manifest.json"
OPTIONS_FILE_NAME = "options.json"
IMPORT_OPTION_KEYS = frozenset(
    {
        "migration_import_file",
        "migration_import_sha256",
        "migration_import_confirmation",
    }
)
MAX_MANIFEST_BYTES = 64 * 1024
MAX_OPTIONS_BYTES = 1024 * 1024
MAX_STATE_BYTES = 2 * 1024 * 1024 * 1024


def canonical_options(options: Mapping[str, object]) -> bytes:
    """Encode operational options without import-only confirmation fields."""
    filtered = {
        key: value
        for key, value in options.items()
        if key not in IMPORT_OPTION_KEYS
    }
    if not all(isinstance(key, str) for key in filtered):
        raise TypeError("option keys must be strings")
    return (
        json.dumps(
            filtered,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_archive(
    path: Path,
    application_version: str,
    timestamp: datetime,
    state_name: str,
    state: bytes,
    options: bytes,
) -> None:
    """Write one complete version-1 migration ZIP without overwriting."""
    manifest = _manifest_bytes(
        application_version,
        timestamp,
        state_name,
        state,
        options,
    )
    with zipfile.ZipFile(
        path,
        "x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        archive.writestr(MANIFEST_FILE_NAME, manifest)
        archive.writestr(OPTIONS_FILE_NAME, options)
        archive.writestr(state_name, state)


def read_archive(path: Path) -> tuple[dict[str, object], bytes, str, bytes]:
    """Read and completely validate one migration ZIP."""
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise MigrationArchiveError("migration archive contains duplicate members")
        if MANIFEST_FILE_NAME not in names:
            raise MigrationArchiveError("migration archive has no manifest")
        manifest_bytes = _read_member(
            archive, MANIFEST_FILE_NAME, MAX_MANIFEST_BYTES
        )
        manifest = _parse_manifest(manifest_bytes)
        state = cast(dict[str, object], manifest["state"])
        state_name = cast(str, state["name"])
        expected = {MANIFEST_FILE_NAME, OPTIONS_FILE_NAME, state_name}
        if set(names) != expected:
            raise MigrationArchiveError("migration archive contains unexpected members")
        options = _read_member(archive, OPTIONS_FILE_NAME, MAX_OPTIONS_BYTES)
        state_bytes = _read_member(archive, state_name, MAX_STATE_BYTES)
        _verify_payload(cast(dict[str, object], manifest["options"]), options)
        _verify_payload(state, state_bytes)
        validate_state_bytes(state_name, state_bytes)
        return manifest, options, state_name, state_bytes


def _manifest_bytes(
    application_version: str,
    timestamp: datetime,
    state_name: str,
    state: bytes,
    options: bytes,
) -> bytes:
    document = {
        "schema_version": SCHEMA_VERSION,
        "application_version": application_version,
        "created_at": timestamp.isoformat(),
        "state": _payload_description(state_name, state),
        "options": _payload_description(OPTIONS_FILE_NAME, options),
    }
    return (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _payload_description(name: str, payload: bytes) -> dict[str, object]:
    return {"name": name, "size": len(payload), "sha256": sha256(payload)}


def _read_member(archive: zipfile.ZipFile, name: str, maximum: int) -> bytes:
    info = archive.getinfo(name)
    if info.is_dir() or info.file_size > maximum:
        raise MigrationArchiveError(f"invalid migration member size: {name}")
    payload = archive.read(info)
    if len(payload) != info.file_size:
        raise MigrationArchiveError(f"incomplete migration member: {name}")
    return payload


def _parse_manifest(payload: bytes) -> dict[str, object]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationArchiveError("migration manifest is invalid JSON") from error
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "application_version",
        "created_at",
        "state",
        "options",
    }:
        raise MigrationArchiveError("migration manifest has invalid fields")
    if document["schema_version"] != SCHEMA_VERSION:
        raise MigrationArchiveError("migration manifest schema is unsupported")
    if not isinstance(document["application_version"], str) or not cast(
        str, document["application_version"]
    ).strip():
        raise MigrationArchiveError("migration application version is invalid")
    try:
        created_at = datetime.fromisoformat(cast(str, document["created_at"]))
    except (TypeError, ValueError) as error:
        raise MigrationArchiveError("migration creation timestamp is invalid") from error
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise MigrationArchiveError("migration creation timestamp must be timezone-aware")
    _validate_payload_description(document["state"], set(STATE_FILE_NAMES))
    _validate_payload_description(document["options"], {OPTIONS_FILE_NAME})
    return cast(dict[str, object], document)


def _validate_payload_description(value: object, names: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != {"name", "size", "sha256"}:
        raise MigrationArchiveError("migration payload description is invalid")
    if value["name"] not in names:
        raise MigrationArchiveError("migration payload name is invalid")
    size = value["size"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise MigrationArchiveError("migration payload size is invalid")
    digest = value["sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise MigrationArchiveError("migration payload SHA-256 is invalid")


def _verify_payload(description: dict[str, object], payload: bytes) -> None:
    if description["size"] != len(payload):
        raise MigrationArchiveError("migration payload size does not match")
    if description["sha256"] != sha256(payload):
        raise MigrationArchiveError("migration payload SHA-256 does not match")
