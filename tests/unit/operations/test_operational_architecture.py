"""Architecture boundary checks for deterministic operational Core."""

import ast
from pathlib import Path


def test_core_operations_has_no_outer_or_side_effect_dependencies() -> None:
    """Keep operational decisions deterministic and infrastructure-free."""
    package = Path(__file__).parents[3] / "core" / "operations"
    forbidden = {
        "aiohttp",
        "applications",
        "homeassistant",
        "infrastructure",
        "os",
        "pathlib",
        "requests",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
    }
    imports: set[str] = set()
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module.partition(".")[0])
    assert imports.isdisjoint(forbidden)
