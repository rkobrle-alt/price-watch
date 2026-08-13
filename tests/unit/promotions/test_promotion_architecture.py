"""Architecture boundary tests for provider-neutral promotion contracts."""

import ast
from pathlib import Path


def test_core_promotions_has_no_outer_layer_or_side_effect_imports() -> None:
    """Keep promotion contracts deterministic and infrastructure-independent."""
    package = Path(__file__).parents[3] / "core" / "promotions"
    forbidden_roots = {
        "aiohttp",
        "applications",
        "homeassistant",
        "infrastructure",
        "requests",
        "socket",
        "sqlalchemy",
    }
    imported_roots: set[str] = set()

    for module_path in package.glob("*.py"):
        syntax_tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(syntax_tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.partition(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_roots.add(node.module.partition(".")[0])

    assert imported_roots.isdisjoint(forbidden_roots)
