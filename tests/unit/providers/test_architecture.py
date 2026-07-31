"""Architecture boundary tests for the Lidl provider."""

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_core_does_not_depend_on_infrastructure() -> None:
    root = Path(__file__).parents[3]
    imports = {
        imported
        for path in (root / "core").rglob("*.py")
        for imported in _imports(path)
    }

    assert not any(name.startswith("infrastructure") for name in imports)


def test_lidl_provider_respects_approved_boundaries() -> None:
    root = Path(__file__).parents[3]
    provider_root = root / "infrastructure" / "providers" / "lidl"
    imports = {
        imported
        for path in provider_root.glob("*.py")
        for imported in _imports(path)
    }
    forbidden = (
        "applications",
        "core.notifications",
        "core.rules",
        "core.state",
        "infrastructure.notifications",
        "infrastructure.persistence",
    )

    assert not any(name.startswith(forbidden) for name in imports)
