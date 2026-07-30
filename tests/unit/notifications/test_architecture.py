"""Architecture tests for notification dependency and determinism boundaries."""

import ast
from pathlib import Path
from unittest import TestCase


class NotificationArchitectureTests(TestCase):
    """Verify Core purity and Infrastructure ownership of delivery."""

    def setUp(self) -> None:
        """Locate notification source packages."""
        repository_root = Path(__file__).parents[3]
        self.core_notifications = repository_root / "core" / "notifications"
        self.infrastructure_notifications = (
            repository_root / "infrastructure" / "notifications"
        )

    def test_core_notifications_has_only_allowed_dependencies(self) -> None:
        imported_modules = self._imported_modules(self.core_notifications)
        forbidden_roots = {
            "aiohttp",
            "applications",
            "homeassistant",
            "infrastructure",
            "requests",
            "sqlalchemy",
        }

        self.assertTrue(
            all(
                module.partition(".")[0] not in forbidden_roots
                for module in imported_modules
            )
        )

    def test_infrastructure_owns_concrete_console_channel(self) -> None:
        core_source = "".join(
            module.read_text(encoding="utf-8")
            for module in self.core_notifications.rglob("*.py")
        )
        console_channel = (
            self.infrastructure_notifications / "console" / "channel.py"
        )

        self.assertNotIn("ConsoleNotificationChannel", core_source)
        self.assertTrue(console_channel.is_file())

    def test_core_never_reads_time_or_generates_identifiers(self) -> None:
        forbidden_expressions = (
            "datetime.now(",
            "datetime.utcnow(",
            "uuid4(",
            "random.",
        )

        for module_path in self.core_notifications.rglob("*.py"):
            source = module_path.read_text(encoding="utf-8")
            with self.subTest(module=module_path.name):
                for expression in forbidden_expressions:
                    self.assertNotIn(expression, source)

    def test_core_contains_no_side_effect_dependencies(self) -> None:
        imported_modules = self._imported_modules(self.core_notifications)
        forbidden_roots = {"os", "pathlib", "socket", "sqlite3", "subprocess"}

        self.assertTrue(
            all(
                module.partition(".")[0] not in forbidden_roots
                for module in imported_modules
            )
        )

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
