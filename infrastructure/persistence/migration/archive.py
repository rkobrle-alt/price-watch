"""Checksummed transfer for one Home Assistant App state artifact."""

import os
import sqlite3
import tempfile
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from infrastructure.persistence.migration._format import (
    canonical_options,
    read_archive,
    write_archive,
)
from infrastructure.persistence.migration._state import (
    MARKER_FILE_NAME,
    active_state_name,
    completed_import,
    copy_state,
    file_sha256,
    install_state,
    write_marker,
)
from infrastructure.persistence.migration.model import (
    MigrationArchiveError,
    MigrationExportResult,
    STATE_FILE_NAMES,
)

_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024


class ZipMigrationArchive:
    """Export and import one validated App state through a fixed directory."""

    def __init__(self, directory: Path) -> None:
        """Configure the shared migration directory without accessing it."""
        if not isinstance(directory, Path):
            raise TypeError("directory must be a Path")
        self._directory = directory

    def export(
        self,
        data_directory: Path,
        options: Mapping[str, object],
        timestamp: datetime,
        application_version: str,
    ) -> MigrationExportResult:
        """Create a non-overwriting, checksummed snapshot of active App state."""
        _validate_export_arguments(
            data_directory, options, timestamp, application_version
        )
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            _validate_directory(self._directory)
            state_name = active_state_name(
                data_directory,
                options.get("catalog_enabled", False),
            )
            archive_file = self._archive_file(timestamp)
            if archive_file.exists():
                raise MigrationArchiveError(
                    f"migration archive already exists: {archive_file}"
                )
            with tempfile.TemporaryDirectory(
                prefix=".price-watch-export-", dir=self._directory
            ) as temporary_name:
                temporary = Path(temporary_name)
                state_copy = temporary / state_name
                copy_state(data_directory / state_name, state_copy)
                state_bytes = state_copy.read_bytes()
                options_bytes = canonical_options(options)
                temporary_archive = temporary / "bundle.zip"
                write_archive(
                    temporary_archive,
                    application_version,
                    timestamp,
                    state_name,
                    state_bytes,
                    options_bytes,
                )
                os.link(temporary_archive, archive_file)
            return MigrationExportResult(
                archive_file, file_sha256(archive_file), state_name
            )
        except MigrationArchiveError:
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError) as error:
            raise MigrationArchiveError(
                f"cannot export Home Assistant migration state: {error}"
            ) from error

    def import_state(
        self,
        archive_file: str,
        archive_sha256: str,
        data_directory: Path,
        options: Mapping[str, object],
    ) -> None:
        """Validate and atomically install state before the first App cycle."""
        _validate_import_arguments(
            archive_file, archive_sha256, data_directory, options
        )
        source = self._directory / archive_file
        try:
            _validate_directory(self._directory)
            _validate_source(source)
            if file_sha256(source) != archive_sha256:
                raise MigrationArchiveError("migration archive SHA-256 does not match")
            manifest, options_bytes, state_name, state_bytes = read_archive(source)
            if options_bytes != canonical_options(options):
                raise MigrationArchiveError(
                    "current App options do not match the exported options"
                )
            state_digest = cast(dict[str, object], manifest["state"])["sha256"]
            data_directory.mkdir(parents=True, exist_ok=True)
            marker = data_directory / MARKER_FILE_NAME
            target = data_directory / state_name
            other = data_directory / (
                STATE_FILE_NAMES[1]
                if state_name == STATE_FILE_NAMES[0]
                else STATE_FILE_NAMES[0]
            )
            if other.exists() or other.is_symlink():
                raise MigrationArchiveError(
                    f"unrelated App state already exists: {other.name}"
                )
            if completed_import(
                marker, archive_sha256, state_name, state_digest, target
            ):
                return
            if target.is_symlink() or (
                target.exists() and file_sha256(target) != state_digest
            ):
                raise MigrationArchiveError(
                    f"unrelated App state already exists: {state_name}"
                )
            if not target.exists():
                install_state(data_directory, state_name, state_bytes)
            write_marker(
                marker, archive_sha256, state_name, cast(str, state_digest)
            )
        except MigrationArchiveError:
            raise
        except (
            OSError,
            sqlite3.Error,
            ValueError,
            TypeError,
            zipfile.BadZipFile,
            RuntimeError,
        ) as error:
            raise MigrationArchiveError(
                f"cannot import Home Assistant migration state: {error}"
            ) from error

    def _archive_file(self, timestamp: datetime) -> Path:
        normalized = timestamp.astimezone(UTC)
        name = normalized.strftime("price-watch-migration-%Y%m%dT%H%M%S%fZ.zip")
        return self._directory / name


def _validate_export_arguments(
    data_directory: object,
    options: object,
    timestamp: object,
    application_version: object,
) -> None:
    if not isinstance(data_directory, Path):
        raise TypeError("data_directory must be a Path")
    if not isinstance(options, Mapping):
        raise TypeError("options must be a Mapping")
    _validate_timestamp(timestamp)
    if not isinstance(application_version, str):
        raise TypeError("application_version must be a string")
    if not application_version.strip():
        raise ValueError("application_version cannot be blank")


def _validate_import_arguments(
    archive_file: object,
    archive_sha256: object,
    data_directory: object,
    options: object,
) -> None:
    if not isinstance(archive_file, str):
        raise TypeError("archive_file must be a string")
    if (
        not archive_file
        or archive_file in {".", ".."}
        or "/" in archive_file
        or "\\" in archive_file
    ):
        raise ValueError("archive_file must be a non-empty basename")
    if not isinstance(archive_sha256, str):
        raise TypeError("archive_sha256 must be a string")
    if len(archive_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in archive_sha256
    ):
        raise ValueError("archive_sha256 must be a lowercase SHA-256 digest")
    if not isinstance(data_directory, Path):
        raise TypeError("data_directory must be a Path")
    if not isinstance(options, Mapping):
        raise TypeError("options must be a Mapping")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")


def _validate_source(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise MigrationArchiveError("migration archive must be a regular file")
    if path.stat().st_size > _MAX_ARCHIVE_BYTES:
        raise MigrationArchiveError("migration archive exceeds the size limit")


def _validate_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise MigrationArchiveError("migration directory must be a regular directory")
