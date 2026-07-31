"""Tests for scheduler package APIs and dependency direction."""

import ast
import inspect
from pathlib import Path

import applications.scheduler as application_api
import infrastructure.scheduler as infrastructure_api
from applications.scheduler import IntervalScheduler, ScheduleResult
from infrastructure.scheduler import SystemDelay


def test_scheduler_public_apis_are_explicit_and_documented() -> None:
    assert application_api.__all__ == ["IntervalScheduler", "ScheduleResult"]
    assert infrastructure_api.__all__ == ["SystemDelay"]
    assert application_api.IntervalScheduler is IntervalScheduler
    assert application_api.ScheduleResult is ScheduleResult
    assert infrastructure_api.SystemDelay is SystemDelay
    for public_object in (IntervalScheduler, ScheduleResult, SystemDelay):
        assert inspect.getdoc(public_object)


def test_scheduler_dependency_direction() -> None:
    root = Path(__file__).parents[3]
    core_imports = _package_imports(root / "core" / "scheduler")
    application_imports = _package_imports(root / "applications" / "scheduler")
    infrastructure_imports = _package_imports(root / "infrastructure" / "scheduler")

    assert not any(name.startswith("infrastructure") for name in core_imports)
    assert not any(name.startswith("applications") for name in core_imports)
    assert not any(name.startswith("infrastructure") for name in application_imports)
    assert not any(name.startswith("applications.cli") for name in application_imports)
    assert not any(name.startswith("applications") for name in infrastructure_imports)


def _package_imports(package: Path) -> set[str]:
    imports: set[str] = set()
    for module in package.glob("*.py"):
        syntax_tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(syntax_tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module)
    return imports
