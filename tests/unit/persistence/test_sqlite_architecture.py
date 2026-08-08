"""Architecture boundary tests for SQLite persistence."""

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_sqlite_persistence_respects_dependency_boundaries() -> None:
    root = Path(__file__).parents[3]
    package = root / "infrastructure" / "persistence" / "sqlite"
    imports = {
        imported
        for module in package.glob("*.py")
        for imported in _imports(module)
    }
    forbidden = (
        "applications",
        "core.provider",
        "core.rules",
        "homeassistant",
        "infrastructure.http",
        "infrastructure.notifications",
        "infrastructure.providers",
        "sqlalchemy",
    )

    assert not any(name.startswith(forbidden) for name in imports)


def test_sqlite_persistence_has_no_hidden_time_uuid_or_environment_reads() -> None:
    root = Path(__file__).parents[3]
    package = root / "infrastructure" / "persistence" / "sqlite"

    for module in package.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "datetime.now(" not in source
        assert "datetime.utcnow(" not in source
        assert "uuid4(" not in source
        assert "os.environ" not in source
        assert "getenv(" not in source
