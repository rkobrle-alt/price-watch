"""Tests for checksummed Home Assistant migration archives."""

import hashlib
import json
import sqlite3
import zipfile
from contextlib import closing
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from infrastructure.persistence.migration import (
    MigrationArchiveError,
    MigrationExportResult,
    ZipMigrationArchive,
)

TIMESTAMP = datetime(2026, 8, 11, 10, 30, 15, 123456, tzinfo=UTC)
OPTIONS = {
    "catalog_enabled": True,
    "notify_entity": "notify.gmail_parkside",
    "interval_seconds": 300,
}


def _catalog(path: Path, value: str = "preserved") -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES (?)", (value,))
        connection.commit()


def _export(tmp_path: Path, *, state: str = "catalog.sqlite3") -> tuple[
    ZipMigrationArchive, MigrationExportResult, Path
]:
    source = tmp_path / "source"
    source.mkdir()
    if state == "catalog.sqlite3":
        _catalog(source / state)
    else:
        (source / state).write_text(
            '{"schema_version":1,"snapshots":{}}\n', encoding="utf-8"
        )
    manager = ZipMigrationArchive(tmp_path / "share")
    return manager, manager.export(source, OPTIONS, TIMESTAMP, "0.27.0"), source


def test_catalog_export_and_import_preserve_database_and_are_idempotent(
    tmp_path: Path,
) -> None:
    manager, result, source = _export(tmp_path)
    target = tmp_path / "target"

    manager.import_state(
        result.archive_file.name,
        result.archive_sha256,
        target,
        OPTIONS,
    )
    manager.import_state(
        result.archive_file.name,
        result.archive_sha256,
        target,
        OPTIONS,
    )

    with closing(sqlite3.connect(target / "catalog.sqlite3")) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == (
            "preserved",
        )
    with closing(sqlite3.connect(source / "catalog.sqlite3")) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == (
            "preserved",
        )
    assert result.archive_file.name == (
        "price-watch-migration-20260811T103015123456Z.zip"
    )
    assert hashlib.sha256(result.archive_file.read_bytes()).hexdigest() == (
        result.archive_sha256
    )
    marker = json.loads(
        (target / ".price-watch-migration.json").read_text(encoding="utf-8")
    )
    assert marker["archive_sha256"] == result.archive_sha256


def test_explicit_json_export_filters_import_options_and_recovers_marker(
    tmp_path: Path,
) -> None:
    manager, result, _ = _export(tmp_path, state="state.json")
    target = tmp_path / "target"
    import_options = {
        **OPTIONS,
        "migration_import_file": result.archive_file.name,
        "migration_import_sha256": result.archive_sha256,
        "migration_import_confirmation": "IMPORT_MIGRATION",
    }

    manager.import_state(
        result.archive_file.name,
        result.archive_sha256,
        target,
        import_options,
    )
    (target / ".price-watch-migration.json").unlink()
    manager.import_state(
        result.archive_file.name,
        result.archive_sha256,
        target,
        import_options,
    )

    assert json.loads((target / "state.json").read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "snapshots": {},
    }
    assert (target / ".price-watch-migration.json").is_file()
    with zipfile.ZipFile(result.archive_file) as archive:
        exported_options = json.loads(archive.read("options.json"))
        manifest = json.loads(archive.read("manifest.json"))
    assert exported_options == OPTIONS
    assert manifest["state"]["name"] == "state.json"
    assert manifest["created_at"] == TIMESTAMP.isoformat()


def test_result_is_frozen_slotted_and_validates_members(tmp_path: Path) -> None:
    result = MigrationExportResult(tmp_path / "x.zip", "a" * 64, "state.json")

    with pytest.raises(FrozenInstanceError):
        result.state_file_name = "catalog.sqlite3"  # type: ignore[misc]
    assert not hasattr(result, "__dict__")

    for values, exception, message in (
        (("x", "a" * 64, "state.json"), TypeError, "archive_file"),
        ((tmp_path / "x", 1, "state.json"), TypeError, "archive_sha256"),
        ((tmp_path / "x", "A" * 64, "state.json"), ValueError, "SHA-256"),
        ((tmp_path / "x", "a" * 64, 1), TypeError, "state_file_name"),
        ((tmp_path / "x", "a" * 64, "other"), ValueError, "unsupported"),
    ):
        with pytest.raises(exception, match=message):
            MigrationExportResult(*cast(tuple, values))


def test_export_rejects_missing_multiple_symlink_and_existing_bundle(
    tmp_path: Path,
) -> None:
    manager = ZipMigrationArchive(tmp_path / "share")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(MigrationArchiveError, match="exactly one"):
        manager.export(empty, OPTIONS, TIMESTAMP, "0.27.0")

    _catalog(empty / "catalog.sqlite3")
    (empty / "state.json").write_text("{}", encoding="utf-8")
    with pytest.raises(MigrationArchiveError, match="exactly one"):
        manager.export(empty, OPTIONS, TIMESTAMP, "0.27.0")

    (empty / "state.json").unlink()
    manager.export(empty, OPTIONS, TIMESTAMP, "0.27.0")
    with pytest.raises(MigrationArchiveError, match="already exists"):
        manager.export(empty, OPTIONS, TIMESTAMP, "0.27.0")


@pytest.mark.parametrize(
    ("arguments", "exception", "message"),
    [
        (("data", OPTIONS, TIMESTAMP, "1"), TypeError, "data_directory"),
        ((Path("data"), [], TIMESTAMP, "1"), TypeError, "options"),
        ((Path("data"), OPTIONS, "now", "1"), TypeError, "timestamp"),
        (
            (Path("data"), OPTIONS, datetime(2026, 1, 1), "1"),
            ValueError,
            "timezone-aware",
        ),
        ((Path("data"), OPTIONS, TIMESTAMP, 1), TypeError, "application_version"),
        ((Path("data"), OPTIONS, TIMESTAMP, " "), ValueError, "cannot be blank"),
    ],
)
def test_export_rejects_invalid_public_arguments(
    tmp_path: Path,
    arguments: tuple[object, ...],
    exception: type[Exception],
    message: str,
) -> None:
    manager = ZipMigrationArchive(tmp_path / "share")
    with pytest.raises(exception, match=message):
        manager.export(*cast(tuple, arguments))


@pytest.mark.parametrize(
    ("arguments", "exception", "message"),
    [
        ((1, "a" * 64, Path("data"), OPTIONS), TypeError, "archive_file"),
        (("../x.zip", "a" * 64, Path("data"), OPTIONS), ValueError, "basename"),
        (("x.zip", 1, Path("data"), OPTIONS), TypeError, "archive_sha256"),
        (("x.zip", "A" * 64, Path("data"), OPTIONS), ValueError, "SHA-256"),
        (("x.zip", "a" * 64, "data", OPTIONS), TypeError, "data_directory"),
        (("x.zip", "a" * 64, Path("data"), []), TypeError, "options"),
    ],
)
def test_import_rejects_invalid_public_arguments(
    tmp_path: Path,
    arguments: tuple[object, ...],
    exception: type[Exception],
    message: str,
) -> None:
    manager = ZipMigrationArchive(tmp_path / "share")
    with pytest.raises(exception, match=message):
        manager.import_state(*cast(tuple, arguments))


def test_import_rejects_missing_bad_digest_options_and_conflicting_state(
    tmp_path: Path,
) -> None:
    manager, result, _ = _export(tmp_path)

    with pytest.raises(MigrationArchiveError, match="regular file"):
        manager.import_state("missing.zip", "a" * 64, tmp_path / "one", OPTIONS)
    with pytest.raises(MigrationArchiveError, match="does not match"):
        manager.import_state(
            result.archive_file.name, "a" * 64, tmp_path / "two", OPTIONS
        )
    with pytest.raises(MigrationArchiveError, match="options do not match"):
        manager.import_state(
            result.archive_file.name,
            result.archive_sha256,
            tmp_path / "three",
            {**OPTIONS, "interval_seconds": 1},
        )

    conflict = tmp_path / "conflict"
    conflict.mkdir()
    (conflict / "state.json").write_text("{}", encoding="utf-8")
    with pytest.raises(MigrationArchiveError, match="unrelated App state"):
        manager.import_state(
            result.archive_file.name,
            result.archive_sha256,
            conflict,
            OPTIONS,
        )

    conflict.joinpath("state.json").unlink()
    (conflict / "catalog.sqlite3").write_bytes(b"different")
    with pytest.raises(MigrationArchiveError, match="unrelated App state"):
        manager.import_state(
            result.archive_file.name,
            result.archive_sha256,
            conflict,
            OPTIONS,
        )


def test_constructor_rejects_invalid_directory() -> None:
    with pytest.raises(TypeError, match="directory"):
        ZipMigrationArchive(cast(Path, "share"))
