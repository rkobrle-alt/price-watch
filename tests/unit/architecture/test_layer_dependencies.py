"""Repository-wide dependency-direction contract tests."""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path
from sys import stdlib_module_names

import pytest


ROOT = Path(__file__).parents[3]
SOURCE_ROOTS = ("core", "infrastructure", "applications")
COMPOSITION_ROOTS = ("applications.cli", "applications.homeassistant")


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolved_import(
    source_module: str,
    source_path: Path,
    imported_module: str | None,
    level: int,
) -> str:
    if level == 0:
        return imported_module or ""
    package = (
        source_module
        if source_path.name == "__init__.py"
        else source_module.rpartition(".")[0]
    )
    relative_name = f"{'.' * level}{imported_module or ''}"
    return resolve_name(relative_name, package)


def _imports(source_module: str, source_path: Path) -> tuple[str, ...]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(
                _resolved_import(
                    source_module,
                    source_path,
                    node.module,
                    node.level,
                )
            )
    return tuple(imports)


def _starts_with(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def _dependency_violation(source_module: str, imported_module: str) -> str | None:
    imported_root = imported_module.partition(".")[0]
    if _starts_with(source_module, "core.domain"):
        if _starts_with(imported_module, "core.domain"):
            return None
        if imported_root in stdlib_module_names:
            return None
        return "Domain may import only Domain and the Python standard library"
    if _starts_with(source_module, "core"):
        if imported_root in {"applications", "infrastructure"}:
            return "Core may not import an outer layer"
        return None
    if _starts_with(source_module, "infrastructure"):
        if imported_root == "applications":
            return "Infrastructure may not import Applications"
        return None
    if _starts_with(source_module, "applications"):
        if any(_starts_with(source_module, root) for root in COMPOSITION_ROOTS):
            return None
        if imported_root == "infrastructure":
            return "Reusable Applications may not import Infrastructure"
    return None


@pytest.mark.parametrize(
    ("source_module", "imported_module", "message"),
    (
        ("core.domain.entities", "core.rules", "Domain may import only Domain"),
        ("core.domain.entities", "decimal", None),
        ("core.rules.engine", "infrastructure.http", "Core may not import"),
        (
            "infrastructure.persistence",
            "applications.synchronization",
            "Infrastructure may not import",
        ),
        (
            "applications.daily_digest.workflow",
            "infrastructure.persistence.sqlite",
            "Reusable Applications may not import",
        ),
        ("applications.cli.composition", "infrastructure.http", None),
        ("applications.homeassistant.composition", "infrastructure.http", None),
    ),
)
def test_dependency_direction_examples(
    source_module: str,
    imported_module: str,
    message: str | None,
) -> None:
    violation = _dependency_violation(source_module, imported_module)

    if message is None:
        assert violation is None
    else:
        assert violation is not None
        assert message in violation


def test_production_tree_respects_dependency_direction() -> None:
    violations: list[str] = []
    for source_root in SOURCE_ROOTS:
        for source_path in sorted((ROOT / source_root).rglob("*.py")):
            source_module = _module_name(source_path)
            for imported_module in _imports(source_module, source_path):
                violation = _dependency_violation(source_module, imported_module)
                if violation is not None:
                    relative_path = source_path.relative_to(ROOT)
                    violations.append(
                        f"{relative_path}: {source_module} -> {imported_module}: "
                        f"{violation}"
                    )

    assert violations == [], "\n".join(violations)
