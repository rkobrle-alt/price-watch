"""Adversarial validation tests for migration archive internals."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

import infrastructure.persistence.migration.archive as archive_module
import infrastructure.persistence.migration._format as format_module
import infrastructure.persistence.migration._state as state_module
from infrastructure.persistence.migration import (
    MigrationArchiveError,
    ZipMigrationArchive,
)
from infrastructure.persistence.json import JsonStateStore
from core.state import StateSnapshot
from tests.unit.notifications.helpers import create_product

TIMESTAMP = datetime(2026, 8, 11, 10, 30, tzinfo=UTC)
DIGEST = "a" * 64


def _payload(name: str) -> dict[str, object]:
    return {"name": name, "size": 0, "sha256": hashlib.sha256(b"").hexdigest()}


def _manifest(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "application_version": "0.27.0",
        "created_at": TIMESTAMP.isoformat(),
        "state": _payload("state.json"),
        "options": _payload("options.json"),
    }
    document.update(overrides)
    return document


def test_export_wraps_filesystem_and_option_encoding_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = ZipMigrationArchive(tmp_path / "share")

    def fail_mkdir(*arguments: object, **keywords: object) -> None:
        raise OSError("share failed")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    with pytest.raises(MigrationArchiveError, match="cannot export") as captured:
        manager.export(tmp_path / "data", {}, TIMESTAMP, "0.27.0")
    assert isinstance(captured.value.__cause__, OSError)
    monkeypatch.undo()

    data = tmp_path / "data"
    data.mkdir()
    (data / "state.json").write_text(
        '{"schema_version":1,"snapshots":{}}', encoding="utf-8"
    )
    with pytest.raises(MigrationArchiveError, match="option keys"):
        manager.export(
            data,
            cast(dict[str, object], {1: "invalid"}),
            TIMESTAMP,
            "0.27.0",
        )


def test_import_wraps_bad_zip_and_rejects_oversized_or_symbolic_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    shared = tmp_path / "share"
    shared.mkdir()
    bad = shared / "bad.zip"
    bad.write_bytes(b"not zip")
    digest = hashlib.sha256(bad.read_bytes()).hexdigest()
    manager = ZipMigrationArchive(shared)

    with pytest.raises(MigrationArchiveError, match="cannot import") as captured:
        manager.import_state("bad.zip", digest, tmp_path / "data", {})
    assert isinstance(captured.value.__cause__, zipfile.BadZipFile)

    monkeypatch.setattr(archive_module, "_MAX_ARCHIVE_BYTES", 0)
    with pytest.raises(MigrationArchiveError, match="size limit"):
        manager.import_state("bad.zip", digest, tmp_path / "data", {})
    monkeypatch.undo()

    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "bad.zip")
    with pytest.raises(MigrationArchiveError, match="regular file"):
        manager.import_state("bad.zip", digest, tmp_path / "data", {})


def test_archive_member_set_validation(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(duplicate, "w") as archive:
        archive.writestr("manifest.json", b"{}")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("manifest.json", b"{}")
    with pytest.raises(MigrationArchiveError, match="duplicate"):
        format_module.read_archive(duplicate)

    missing = tmp_path / "missing.zip"
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("options.json", b"{}")
    with pytest.raises(MigrationArchiveError, match="no manifest"):
        format_module.read_archive(missing)

    unexpected = tmp_path / "unexpected.zip"
    manifest = json.dumps(_manifest()).encode()
    with zipfile.ZipFile(unexpected, "w") as archive:
        archive.writestr("manifest.json", manifest)
        archive.writestr("options.json", b"")
        archive.writestr("state.json", b"")
        archive.writestr("extra", b"")
    with pytest.raises(MigrationArchiveError, match="unexpected members"):
        format_module.read_archive(unexpected)


def test_member_reader_rejects_directory_size_and_incomplete_payload(
    tmp_path: Path,
) -> None:
    path = tmp_path / "members.zip"
    with zipfile.ZipFile(path, "w") as writer:
        writer.writestr("directory/", b"")
        writer.writestr("large", b"12")
    with zipfile.ZipFile(path) as reader:
        with pytest.raises(MigrationArchiveError, match="member size"):
            format_module._read_member(reader, "directory/", 10)
        with pytest.raises(MigrationArchiveError, match="member size"):
            format_module._read_member(reader, "large", 1)

    class Info:
        is_dir = lambda self: False
        file_size = 2

    class IncompleteArchive:
        def getinfo(self, name: str) -> Info:
            return Info()

        def read(self, info: Info) -> bytes:
            return b"1"

    with pytest.raises(MigrationArchiveError, match="incomplete"):
        format_module._read_member(cast(zipfile.ZipFile, IncompleteArchive()), "x", 2)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"{", "invalid JSON"),
        (json.dumps([]).encode(), "invalid fields"),
        (json.dumps(_manifest(schema_version=2)).encode(), "unsupported"),
        (json.dumps(_manifest(application_version=" ")).encode(), "version"),
        (json.dumps(_manifest(application_version=2)).encode(), "version"),
        (json.dumps(_manifest(created_at="bad")).encode(), "timestamp"),
        (
            json.dumps(_manifest(created_at="2026-08-11T10:30:00")).encode(),
            "timezone-aware",
        ),
    ],
)
def test_manifest_rejects_invalid_top_level_values(
    payload: bytes, message: str
) -> None:
    with pytest.raises((MigrationArchiveError, ValueError), match=message):
        format_module._parse_manifest(payload)


@pytest.mark.parametrize(
    ("description", "names", "message"),
    [
        ([], {"x"}, "description"),
        ({"name": "x"}, {"x"}, "description"),
        ({"name": "y", "size": 0, "sha256": DIGEST}, {"x"}, "name"),
        ({"name": "x", "size": True, "sha256": DIGEST}, {"x"}, "size"),
        ({"name": "x", "size": -1, "sha256": DIGEST}, {"x"}, "size"),
        ({"name": "x", "size": 0, "sha256": 1}, {"x"}, "SHA-256"),
        ({"name": "x", "size": 0, "sha256": "A" * 64}, {"x"}, "SHA-256"),
    ],
)
def test_payload_description_rejects_invalid_values(
    description: object, names: set[str], message: str
) -> None:
    with pytest.raises(MigrationArchiveError, match=message):
        format_module._validate_payload_description(description, names)


def test_payload_verification_and_json_state_validation() -> None:
    with pytest.raises(MigrationArchiveError, match="size does not match"):
        format_module._verify_payload(
            {"size": 2, "sha256": hashlib.sha256(b"x").hexdigest()}, b"x"
        )
    with pytest.raises(MigrationArchiveError, match="SHA-256 does not match"):
        format_module._verify_payload({"size": 1, "sha256": DIGEST}, b"x")
    with pytest.raises(MigrationArchiveError, match="invalid"):
        state_module.validate_json_state(b"{")
    with pytest.raises(MigrationArchiveError, match="invalid"):
        state_module.validate_json_state(b"[]")
    invalid_snapshot = {
        "schema_version": 1,
        "snapshots": {"00000000-0000-0000-0000-000000000001": {}},
    }
    with pytest.raises(MigrationArchiveError, match="invalid"):
        state_module.validate_json_state(json.dumps(invalid_snapshot).encode())


def test_json_state_validation_decodes_complete_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    JsonStateStore(path).save(StateSnapshot(create_product(), TIMESTAMP))

    state_module.validate_json_state(path.read_bytes())


def test_active_state_rejects_symbolic_configured_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state = tmp_path / "state.json"
    state.write_text('{"schema_version":1,"snapshots":{}}', encoding="utf-8")
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == state)

    with pytest.raises(MigrationArchiveError, match="regular file"):
        state_module.active_state_name(tmp_path, False)


def test_export_finalization_never_overwrites_racing_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "state.json").write_text(
        '{"schema_version":1,"snapshots":{}}', encoding="utf-8"
    )
    shared = tmp_path / "share"
    original_link = archive_module.os.link

    def race(source: object, destination: object) -> None:
        Path(cast(str, destination)).write_bytes(b"racing export")
        original_link(source, destination)

    monkeypatch.setattr(archive_module.os, "link", race)
    with pytest.raises(MigrationArchiveError, match="cannot export"):
        ZipMigrationArchive(shared).export(data, {}, TIMESTAMP, "0.27.0")

    final = next(shared.glob("price-watch-migration-*.zip"))
    assert final.read_bytes() == b"racing export"


def test_sqlite_integrity_failure_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Cursor:
        def fetchone(self) -> tuple[str]:
            return ("corrupt",)

    class Connection:
        def execute(self, statement: str) -> Cursor:
            return Cursor()

        def close(self) -> None:
            return None

    monkeypatch.setattr(state_module.sqlite3, "connect", lambda *args, **kwargs: Connection())
    with pytest.raises(MigrationArchiveError, match="integrity"):
        state_module.validate_sqlite(tmp_path / "state.sqlite3")


def test_import_marker_rejects_invalid_conflicting_and_changed_state(
    tmp_path: Path,
) -> None:
    marker = tmp_path / ".price-watch-migration.json"
    target = tmp_path / "state.json"
    target.write_bytes(b"state")
    state_digest = hashlib.sha256(b"state").hexdigest()

    marker.write_text("{", encoding="utf-8")
    with pytest.raises(MigrationArchiveError, match="marker is invalid"):
        state_module.completed_import(
            marker, DIGEST, "state.json", state_digest, target
        )

    marker.write_text("{}", encoding="utf-8")
    with pytest.raises(MigrationArchiveError, match="conflicts"):
        state_module.completed_import(
            marker, DIGEST, "state.json", state_digest, target
        )

    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "archive_sha256": DIGEST,
                "state_file_name": "state.json",
                "state_sha256": DIGEST,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(MigrationArchiveError, match="does not match its marker"):
        state_module.completed_import(marker, DIGEST, "state.json", DIGEST, target)


def test_import_marker_rejects_symbolic_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / ".price-watch-migration.json"
    target = tmp_path / "state.json"
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == marker)

    with pytest.raises(MigrationArchiveError, match="conflicts"):
        state_module.completed_import(marker, DIGEST, "state.json", DIGEST, target)
