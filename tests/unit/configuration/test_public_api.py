"""Tests for configuration APIs and dependency direction."""

import ast
import inspect
from pathlib import Path

import applications.configuration as application_api
import core.configuration as core_api
import infrastructure.configuration.toml as infrastructure_api
from applications.configuration import ApplicationConfig, parse_configuration
from core.configuration import ConfigurationError, ConfigurationLoader
from infrastructure.configuration.toml import TomlConfigurationLoader


def test_configuration_public_apis_are_explicit_and_documented() -> None:
    assert core_api.__all__ == ["ConfigurationError", "ConfigurationLoader"]
    assert application_api.__all__ == ["ApplicationConfig", "parse_configuration"]
    assert infrastructure_api.__all__ == ["TomlConfigurationLoader"]
    assert core_api.ConfigurationError is ConfigurationError
    assert core_api.ConfigurationLoader is ConfigurationLoader
    assert application_api.ApplicationConfig is ApplicationConfig
    assert application_api.parse_configuration is parse_configuration
    assert infrastructure_api.TomlConfigurationLoader is TomlConfigurationLoader
    for public_object in (
        ConfigurationError,
        ConfigurationLoader,
        ApplicationConfig,
        parse_configuration,
        TomlConfigurationLoader,
    ):
        assert inspect.getdoc(public_object)


def test_configuration_dependency_direction() -> None:
    root = Path(__file__).parents[3]
    core_imports = _package_imports(root / "core" / "configuration")
    application_imports = _package_imports(root / "applications" / "configuration")
    infrastructure_imports = _package_imports(
        root / "infrastructure" / "configuration"
    )

    assert not any(name.startswith("applications") for name in core_imports)
    assert not any(name.startswith("infrastructure") for name in core_imports)
    assert not any(name.startswith("infrastructure") for name in application_imports)
    assert not any(name.startswith("applications") for name in infrastructure_imports)


def _package_imports(package: Path) -> set[str]:
    imports: set[str] = set()
    for module in package.rglob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module)
    return imports
