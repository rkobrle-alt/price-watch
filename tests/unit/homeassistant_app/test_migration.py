"""Tests for Home Assistant migration option and command values."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from applications.homeassistant import (
    HomeAssistantConfig,
    HomeAssistantMigrationExportCommand,
    HomeAssistantMigrationImport,
    MigrationCommandError,
    parse_homeassistant_options,
    parse_migration_export_command,
)
from core.configuration import ConfigurationError
from tests.unit.homeassistant_app.helpers import create_options
from tests.unit.homeassistant_app.helpers import create_config

SHA256 = "a" * 64


def test_import_value_is_frozen_slotted_and_parsed_from_complete_options() -> None:
    options = create_options(
        migration_import_file="price-watch-migration.zip",
        migration_import_sha256=SHA256,
        migration_import_confirmation="IMPORT_MIGRATION",
    )

    result = parse_homeassistant_options(options, Path("/data"))

    assert result.migration_import == HomeAssistantMigrationImport(
        "price-watch-migration.zip",
        SHA256,
    )
    with pytest.raises(FrozenInstanceError):
        result.migration_import.archive_file = "other.zip"  # type: ignore[misc]
    assert not hasattr(result.migration_import, "__dict__")
    assert parse_homeassistant_options(create_options(), Path("/data")).migration_import is None


@pytest.mark.parametrize(
    ("values", "exception", "message"),
    [
        ((1, SHA256), TypeError, "archive_file"),
        (("", SHA256), ValueError, "basename"),
        ((".", SHA256), ValueError, "basename"),
        (("../state.zip", SHA256), ValueError, "basename"),
        (("folder\\state.zip", SHA256), ValueError, "basename"),
        (("state.zip", 1), TypeError, "archive_sha256"),
        (("state.zip", "A" * 64), ValueError, "SHA-256"),
        (("state.zip", "a" * 63), ValueError, "SHA-256"),
    ],
)
def test_import_value_rejects_invalid_members(
    values: tuple[object, object],
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        HomeAssistantMigrationImport(*cast(tuple, values))


def test_homeassistant_config_rejects_invalid_migration_import_type() -> None:
    current = create_config()
    with pytest.raises(TypeError, match="migration_import"):
        HomeAssistantConfig(
            current.application,
            current.notify_entity,
            migration_import=cast(HomeAssistantMigrationImport, object()),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"migration_import_file": "bundle.zip"}, "missing keys"),
        (
            {
                "migration_import_file": "bundle.zip",
                "migration_import_sha256": SHA256,
                "migration_import_confirmation": 1,
            },
            "confirmation",
        ),
        (
            {
                "migration_import_file": "bundle.zip",
                "migration_import_sha256": SHA256,
                "migration_import_confirmation": "import_migration",
            },
            "IMPORT_MIGRATION",
        ),
        (
            {
                "migration_import_file": 1,
                "migration_import_sha256": SHA256,
                "migration_import_confirmation": "IMPORT_MIGRATION",
            },
            "archive_file",
        ),
    ],
)
def test_parser_rejects_invalid_import_options(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_homeassistant_options(create_options(**overrides), Path("/data"))


def test_export_command_is_frozen_slotted_and_accepts_exact_object() -> None:
    command = parse_migration_export_command(
        '{"command":"export_migration","confirmation":"EXPORT_MIGRATION"}\n'
    )

    assert command == HomeAssistantMigrationExportCommand()
    assert not hasattr(command, "__dict__")


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("", "blank"),
        ("{", "valid JSON"),
        ("[]", "JSON object"),
        ('{"command":"export_migration"}', "missing fields"),
        (
            '{"command":"export_migration","confirmation":"EXPORT_MIGRATION","x":1}',
            "unknown fields",
        ),
        (
            '{"command":"other","confirmation":"EXPORT_MIGRATION"}',
            "command must be",
        ),
        (
            '{"command":"export_migration","confirmation":"wrong"}',
            "confirmation must be",
        ),
        (
            '{"command":"export_migration","command":"export_migration",'
            '"confirmation":"EXPORT_MIGRATION"}',
            "duplicate field",
        ),
    ],
)
def test_export_command_rejects_invalid_external_data(
    line: str, message: str
) -> None:
    with pytest.raises(MigrationCommandError, match=message):
        parse_migration_export_command(line)


def test_export_command_rejects_invalid_public_type() -> None:
    with pytest.raises(TypeError, match="line"):
        parse_migration_export_command(cast(str, 1))
