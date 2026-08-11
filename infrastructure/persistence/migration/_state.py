"""Validate and atomically transfer migration state artifacts."""

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from infrastructure.persistence.migration.model import (
    MigrationArchiveError,
    STATE_FILE_NAMES,
)
from infrastructure.persistence.json.codec import (
    SnapshotCodecError,
    decode_snapshot,
    snapshot_entries,
    validate_document,
)

SCHEMA_VERSION = 1
MARKER_FILE_NAME = ".price-watch-migration.json"


def active_state_name(data_directory: Path) -> str:
    """Return the only regular supported state artifact."""
    active = [
        name
        for name in STATE_FILE_NAMES
        if (data_directory / name).is_file()
        and not (data_directory / name).is_symlink()
    ]
    if len(active) != 1:
        raise MigrationArchiveError(
            "exactly one regular active state file is required"
        )
    return active[0]


def copy_state(source: Path, destination: Path) -> None:
    """Create and validate one consistent state copy."""
    if source.name == "catalog.sqlite3":
        with closing(sqlite3.connect(source)) as source_connection:
            with closing(sqlite3.connect(destination)) as destination_connection:
                source_connection.backup(destination_connection)
        validate_sqlite(destination)
        return
    payload = source.read_bytes()
    validate_json_state(payload)
    destination.write_bytes(payload)


def validate_state_bytes(state_name: str, payload: bytes) -> None:
    """Validate one state payload using its approved format."""
    if state_name == "catalog.sqlite3":
        with tempfile.TemporaryDirectory(
            prefix=".price-watch-validate-"
        ) as directory:
            path = Path(directory) / state_name
            path.write_bytes(payload)
            validate_sqlite(path)
        return
    validate_json_state(payload)


def validate_json_state(payload: bytes) -> None:
    """Decode every snapshot in one schema-v1 JSON state document."""
    try:
        document = validate_document(json.loads(payload))
        for storage_key, snapshot in snapshot_entries(document).items():
            decode_snapshot(snapshot, storage_key)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        SnapshotCodecError,
    ) as error:
        raise MigrationArchiveError("migration JSON state is invalid") from error


def validate_sqlite(path: Path) -> None:
    """Require SQLite to report a complete integrity check."""
    with closing(
        sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    ) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    if result != ("ok",):
        raise MigrationArchiveError("migration SQLite integrity check failed")


def install_state(directory: Path, state_name: str, payload: bytes) -> None:
    """Validate, synchronize and atomically install one state file."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{state_name}.",
        suffix=".tmp",
        dir=directory,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if state_name == "catalog.sqlite3":
            validate_sqlite(temporary)
        else:
            validate_json_state(temporary.read_bytes())
        os.link(temporary, directory / state_name)
    finally:
        temporary.unlink(missing_ok=True)


def completed_import(
    marker: Path,
    archive_digest: str,
    state_name: str,
    state_digest: object,
    target: Path,
) -> bool:
    """Validate an existing completion marker and installed state."""
    if marker.is_symlink():
        raise MigrationArchiveError("migration import marker conflicts with App state")
    if not marker.exists():
        return False
    try:
        document = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationArchiveError("migration import marker is invalid") from error
    expected = {
        "schema_version": SCHEMA_VERSION,
        "archive_sha256": archive_digest,
        "state_file_name": state_name,
        "state_sha256": state_digest,
    }
    if document != expected or not target.is_file() or target.is_symlink():
        raise MigrationArchiveError("migration import marker conflicts with App state")
    if file_sha256(target) != state_digest:
        raise MigrationArchiveError("imported App state does not match its marker")
    return True


def write_marker(
    marker: Path,
    archive_digest: str,
    state_name: str,
    state_digest: str,
) -> None:
    """Atomically record one completed import."""
    payload = (
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "archive_sha256": archive_digest,
                "state_file_name": state_name,
                "state_sha256": state_digest,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{marker.name}.",
        suffix=".tmp",
        dir=marker.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, marker)
    finally:
        temporary.unlink(missing_ok=True)


def sha256(payload: bytes) -> str:
    """Return the lowercase SHA-256 of an in-memory payload."""
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    """Return the lowercase SHA-256 of one file without loading it whole."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
