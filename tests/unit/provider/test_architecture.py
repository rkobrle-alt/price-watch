"""Architecture tests for Provider SDK dependency boundaries."""

import ast
from pathlib import Path
from unittest import TestCase


class ProviderArchitectureTests(TestCase):
    """Verify Provider SDK imports remain transport and application neutral."""

    def test_provider_sdk_has_no_forbidden_imports(self) -> None:
        repository_root = Path(__file__).parents[3]
        provider_package = repository_root / "core" / "provider"
        forbidden_roots = {
            "aiohttp",
            "apps",
            "bs4",
            "homeassistant",
            "requests",
            "sqlalchemy",
        }

        imported_roots: set[str] = set()
        for module_path in provider_package.glob("*.py"):
            syntax_tree = ast.parse(module_path.read_text(encoding="utf-8"))
            for node in ast.walk(syntax_tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(
                        alias.name.partition(".")[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_roots.add(node.module.partition(".")[0])

        self.assertTrue(imported_roots.isdisjoint(forbidden_roots))
