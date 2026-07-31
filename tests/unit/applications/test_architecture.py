"""Architecture boundary tests for synchronization applications."""

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    syntax_tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(syntax_tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_synchronization_depends_only_on_public_core_and_standard_library() -> None:
    root = Path(__file__).parents[3]
    package = root / "applications" / "synchronization"
    imports = {
        imported
        for module in package.glob("*.py")
        for imported in _imports(module)
    }
    forbidden = (
        "applications.cli",
        "applications.homeassistant",
        "aiohttp",
        "homeassistant",
        "infrastructure",
        "sqlalchemy",
    )

    assert not any(name.startswith(forbidden) for name in imports)


def test_core_and_infrastructure_do_not_depend_on_applications() -> None:
    root = Path(__file__).parents[3]
    imports = {
        imported
        for package_name in ("core", "infrastructure")
        for module in (root / package_name).rglob("*.py")
        for imported in _imports(module)
    }

    assert not any(name.startswith("applications") for name in imports)


def test_synchronization_has_no_hidden_time_randomness_or_io() -> None:
    root = Path(__file__).parents[3]
    package = root / "applications" / "synchronization"

    for module in package.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "datetime.now(" not in source
        assert "datetime.utcnow(" not in source
        assert "uuid4(" not in source
        assert "os.environ" not in source
        assert "getenv(" not in source
        assert "open(" not in source
