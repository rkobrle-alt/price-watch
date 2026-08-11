"""Public API and dependency tests for the Home Assistant App."""

import ast
import inspect
import runpy
from pathlib import Path

import pytest

import applications.homeassistant as homeassistant_api
import infrastructure.configuration.json as json_api
from applications.cli import VERSION as CLI_VERSION
from applications.homeassistant import (
    HomeAssistantConfig,
    HomeAssistantMaintenanceCommand,
    HomeAssistantMigrationExportCommand,
    HomeAssistantMigrationImport,
    MaintenanceCommandError,
    MaintenanceCommandProcessor,
    MaintenanceCommandResult,
    MaintenanceCommandStatus,
    MigrationCommandError,
    main,
    parse_maintenance_command,
    parse_migration_export_command,
    parse_homeassistant_options,
    run,
)
from applications.version import VERSION
from infrastructure.configuration.json import JsonConfigurationLoader
from infrastructure.persistence.migration import (
    MigrationArchiveError,
    MigrationExportResult,
    ZipMigrationArchive,
)


def test_public_apis_are_explicit_documented_and_versioned_once() -> None:
    assert homeassistant_api.__all__ == [
        "HomeAssistantConfig",
        "HomeAssistantMaintenanceCommand",
        "HomeAssistantMigrationExportCommand",
        "HomeAssistantMigrationImport",
        "MaintenanceCommandError",
        "MaintenanceCommandProcessor",
        "MaintenanceCommandResult",
        "MaintenanceCommandStatus",
        "MigrationCommandError",
        "main",
        "parse_maintenance_command",
        "parse_migration_export_command",
        "parse_homeassistant_options",
        "run",
    ]
    assert json_api.__all__ == ["JsonConfigurationLoader"]
    assert homeassistant_api.HomeAssistantConfig is HomeAssistantConfig
    assert homeassistant_api.main is main
    assert homeassistant_api.parse_homeassistant_options is parse_homeassistant_options
    assert homeassistant_api.run is run
    assert json_api.JsonConfigurationLoader is JsonConfigurationLoader
    assert CLI_VERSION == VERSION
    for exception in (
        MaintenanceCommandError,
        MigrationArchiveError,
        MigrationCommandError,
    ):
        assert inspect.getdoc(exception)
    for public_object in (
        HomeAssistantConfig,
        HomeAssistantMaintenanceCommand,
        HomeAssistantMigrationExportCommand,
        HomeAssistantMigrationImport,
        MaintenanceCommandProcessor,
        MaintenanceCommandResult,
        MaintenanceCommandStatus,
        MigrationExportResult,
        ZipMigrationArchive,
        JsonConfigurationLoader,
        main,
        parse_maintenance_command,
        parse_migration_export_command,
        parse_homeassistant_options,
        run,
    ):
        assert inspect.getdoc(public_object)
        assert inspect.signature(public_object)


def test_module_execution_delegates_to_public_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(homeassistant_api, "main", lambda: 23)

    with pytest.raises(SystemExit) as captured:
        runpy.run_module("applications.homeassistant.__main__", run_name="__main__")

    assert captured.value.code == 23


def test_homeassistant_application_dependency_direction() -> None:
    root = Path(__file__).parents[3]
    core_imports = _imports(root / "core")
    infrastructure_imports = _imports(root / "infrastructure" / "configuration" / "json")
    infrastructure_imports |= _imports(root / "infrastructure" / "persistence" / "migration")
    cli_imports = _imports(root / "applications" / "cli")
    reusable_imports = _imports(root / "applications" / "synchronization") | _imports(
        root / "applications" / "scheduler"
    )

    assert not any(name.startswith("applications") for name in core_imports)
    assert not any(name.startswith("infrastructure") for name in core_imports)
    assert not any(name.startswith("applications") for name in infrastructure_imports)
    assert not any(name.startswith("applications.homeassistant") for name in cli_imports)
    assert not any(name.startswith("applications.homeassistant") for name in reusable_imports)
    assert not any(name.startswith("infrastructure") for name in reusable_imports)


def test_secret_access_exists_only_at_process_boundary() -> None:
    root = Path(__file__).parents[3]
    package = root / "applications" / "homeassistant"
    occurrences: list[Path] = []
    for module in package.glob("*.py"):
        if "SUPERVISOR_TOKEN" in module.read_text(encoding="utf-8"):
            occurrences.append(module)

    assert occurrences == [package / "main.py"]
    for package_path in (
        root / "core",
        root / "infrastructure",
    ):
        assert all(
            "SUPERVISOR_TOKEN" not in module.read_text(encoding="utf-8")
            for module in package_path.rglob("*.py")
        )


def _imports(package: Path) -> set[str]:
    imports: set[str] = set()
    for module in package.rglob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module)
    return imports
