"""Architecture tests for State Store dependency and side-effect rules."""

import ast
from pathlib import Path
from unittest import TestCase


class StateStoreArchitectureTests(TestCase):
    """Verify Core abstractions and Infrastructure implementation boundaries."""

    def setUp(self) -> None:
        """Locate State Store source packages."""
        repository_root = Path(__file__).parents[3]
        self.core_state = repository_root / "core" / "state"
        self.memory_state = (
            repository_root / "infrastructure" / "persistence" / "memory"
        )

    def test_core_state_does_not_import_infrastructure(self) -> None:
        imported_modules = self._imported_modules(self.core_state)

        self.assertTrue(
            all(
                module != "infrastructure"
                and not module.startswith("infrastructure.")
                for module in imported_modules
            )
        )

    def test_memory_store_has_no_forbidden_dependencies(self) -> None:
        imported_modules = self._imported_modules(self.memory_state)
        forbidden_roots = {
            "aiohttp",
            "homeassistant",
            "os",
            "pathlib",
            "requests",
            "sqlalchemy",
        }

        self.assertTrue(
            all(
                module.partition(".")[0] not in forbidden_roots
                for module in imported_modules
            )
        )

    def test_state_store_never_reads_system_clock(self) -> None:
        for package in (self.core_state, self.memory_state):
            for module_path in package.rglob("*.py"):
                source = module_path.read_text(encoding="utf-8")
                with self.subTest(module=module_path):
                    self.assertNotIn("datetime.now(", source)
                    self.assertNotIn("datetime.utcnow(", source)

    def test_snapshot_has_no_state_store_error_dependency(self) -> None:
        snapshot_source = (self.core_state / "snapshot.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("StateStoreError", snapshot_source)

    @staticmethod
    def _imported_modules(package: Path) -> set[str]:
        imported_modules: set[str] = set()
        for module_path in package.rglob("*.py"):
            syntax_tree = ast.parse(module_path.read_text(encoding="utf-8"))
            for node in ast.walk(syntax_tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_modules.add(node.module)
        return imported_modules
