"""Validate explicit Home Assistant App migration requests."""

import json
import re
from dataclasses import dataclass
from typing import cast

from core.configuration import ConfigurationError

_EXPORT_COMMAND = "export_migration"
_EXPORT_CONFIRMATION = "EXPORT_MIGRATION"
_IMPORT_CONFIRMATION = "IMPORT_MIGRATION"
_EXPORT_FIELDS = frozenset({"command", "confirmation"})
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class MigrationCommandError(RuntimeError):
    """Report invalid external Home Assistant migration command data."""


@dataclass(frozen=True, slots=True)
class HomeAssistantMigrationImport:
    """Identify one explicitly confirmed migration archive import."""

    archive_file: str
    archive_sha256: str

    def __post_init__(self) -> None:
        """Validate the immutable import request."""
        if not isinstance(self.archive_file, str):
            raise TypeError("archive_file must be a string")
        if (
            not self.archive_file
            or self.archive_file in {".", ".."}
            or "/" in self.archive_file
            or "\\" in self.archive_file
        ):
            raise ValueError("archive_file must be a non-empty basename")
        if not isinstance(self.archive_sha256, str):
            raise TypeError("archive_sha256 must be a string")
        if _SHA256_PATTERN.fullmatch(self.archive_sha256) is None:
            raise ValueError("archive_sha256 must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class HomeAssistantMigrationExportCommand:
    """Request one read-only export of the active App state."""


def parse_migration_export_command(
    line: str,
) -> HomeAssistantMigrationExportCommand:
    """Parse one strict JSON-lines migration export command."""
    if not isinstance(line, str):
        raise TypeError("line must be a string")
    if not line.strip():
        raise MigrationCommandError("migration command cannot be blank")
    try:
        document = json.loads(line, object_pairs_hook=_strict_object)
    except json.JSONDecodeError as error:
        raise MigrationCommandError("migration command must be valid JSON") from error
    if not isinstance(document, dict):
        raise MigrationCommandError("migration command must be a JSON object")
    keys = set(document)
    if keys != _EXPORT_FIELDS:
        missing = sorted(_EXPORT_FIELDS - keys)
        unknown = sorted(keys - _EXPORT_FIELDS)
        detail = []
        if missing:
            detail.append(f"missing fields: {', '.join(missing)}")
        if unknown:
            detail.append(f"unknown fields: {', '.join(unknown)}")
        raise MigrationCommandError("; ".join(detail))
    if document["command"] != _EXPORT_COMMAND:
        raise MigrationCommandError(f"command must be {_EXPORT_COMMAND!r}")
    if document["confirmation"] != _EXPORT_CONFIRMATION:
        raise MigrationCommandError(
            f"confirmation must be {_EXPORT_CONFIRMATION!r}"
        )
    return HomeAssistantMigrationExportCommand()


def _parse_migration_import(
    document: dict[str, object],
) -> HomeAssistantMigrationImport | None:
    """Convert the optional three-field import request from App options."""
    fields = {
        "migration_import_file",
        "migration_import_sha256",
        "migration_import_confirmation",
    }
    present = fields & set(document)
    if not present:
        return None
    if present != fields:
        missing = ", ".join(sorted(fields - present))
        raise ConfigurationError(f"migration import is missing keys: {missing}")
    confirmation = document["migration_import_confirmation"]
    if not isinstance(confirmation, str):
        raise TypeError("migration_import_confirmation must be a string")
    if confirmation != _IMPORT_CONFIRMATION:
        raise ValueError(
            f"migration_import_confirmation must be {_IMPORT_CONFIRMATION!r}"
        )
    return HomeAssistantMigrationImport(
        cast(str, document["migration_import_file"]),
        cast(str, document["migration_import_sha256"]),
    )


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MigrationCommandError(f"duplicate field: {key}")
        result[key] = value
    return result
