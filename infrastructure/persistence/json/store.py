"""Atomic JSON-file implementation of the State Store contract."""

import json
from os import fsync, replace
from pathlib import Path
from tempfile import NamedTemporaryFile

from core.domain import ProductId
from core.state import StateSnapshot, StateStoreError
from infrastructure.persistence.json.codec import (
    SnapshotCodecError,
    create_document,
    decode_snapshot,
    encode_snapshot,
    snapshot_entries,
    validate_document,
)


class JsonStateStore:
    """Persist the latest product snapshots in one atomic JSON document."""

    def __init__(self, path: Path) -> None:
        """Configure the destination path without accessing the filesystem."""
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        self._path = path

    def load(self, product_id: ProductId) -> StateSnapshot | None:
        """Load the latest snapshot for a product identifier."""
        if not isinstance(product_id, ProductId):
            raise TypeError("product_id must be a ProductId")

        document = self._read_document()
        if document is None:
            return None
        storage_key = str(product_id.value)
        stored_snapshot = snapshot_entries(document).get(storage_key)
        if stored_snapshot is None:
            return None
        try:
            return decode_snapshot(stored_snapshot, storage_key)
        except SnapshotCodecError as error:
            raise StateStoreError(
                f"failed to decode product snapshot from {self._path}"
            ) from error

    def save(self, snapshot: StateSnapshot) -> None:
        """Atomically save a snapshot using its product identifier as the key."""
        if not isinstance(snapshot, StateSnapshot):
            raise TypeError("snapshot must be a StateSnapshot")

        document = self._read_document()
        if document is None:
            document = create_document()
        snapshot_entries(document)[str(snapshot.product.id.value)] = encode_snapshot(
            snapshot
        )
        self._write_document(document)

    def _read_document(self) -> dict[str, object] | None:
        try:
            content = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError) as error:
            raise StateStoreError(f"failed to read state from {self._path}") from error

        try:
            return validate_document(json.loads(content))
        except (json.JSONDecodeError, SnapshotCodecError) as error:
            raise StateStoreError(f"invalid state document at {self._path}") from error

    def _write_document(self, document: dict[str, object]) -> None:
        content = json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        temporary_path: Path | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
                temporary_file.flush()
                fsync(temporary_file.fileno())
            replace(temporary_path, self._path)
        except OSError as error:
            if temporary_path is not None:
                _remove_temporary_file(temporary_path)
            raise StateStoreError(f"failed to write state to {self._path}") from error


def _remove_temporary_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return
