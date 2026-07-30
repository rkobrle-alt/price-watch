"""Public API and dependency tests for the Rule Engine."""

import ast
from pathlib import Path
from unittest import TestCase

import core.rules as rules_api


class RulePublicApiTests(TestCase):
    """Verify the documented Rule Engine package exports."""

    def test_public_exports(self) -> None:
        expected = {
            "EvaluationResult",
            "EvaluatorRegistry",
            "RuleEngine",
            "RuleError",
            "RuleEvaluator",
        }

        self.assertEqual(set(rules_api.__all__), expected)
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue(getattr(rules_api, name).__doc__)


class RuleArchitectureTests(TestCase):
    """Verify Rule Engine dependency and determinism boundaries."""

    def test_rule_engine_uses_only_standard_library_and_domain(self) -> None:
        repository_root = Path(__file__).parents[3]
        rules_package = repository_root / "core" / "rules"
        forbidden_roots = {
            "aiohttp",
            "apps",
            "core.provider",
            "homeassistant",
            "requests",
            "sqlalchemy",
        }
        imported_modules: set[str] = set()

        for module_path in rules_package.rglob("*.py"):
            syntax_tree = ast.parse(module_path.read_text(encoding="utf-8"))
            for node in ast.walk(syntax_tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_modules.add(node.module)

        self.assertTrue(
            all(
                not any(
                    module == forbidden or module.startswith(f"{forbidden}.")
                    for forbidden in forbidden_roots
                )
                for module in imported_modules
            )
        )

    def test_core_rules_never_reads_system_clock(self) -> None:
        repository_root = Path(__file__).parents[3]
        rules_package = repository_root / "core" / "rules"

        for module_path in rules_package.rglob("*.py"):
            source = module_path.read_text(encoding="utf-8")
            with self.subTest(module=module_path.name):
                self.assertNotIn("datetime.now(", source)
                self.assertNotIn("datetime.utcnow(", source)

    def test_engine_contains_no_rule_type_business_logic(self) -> None:
        repository_root = Path(__file__).parents[3]
        engine_source = (
            repository_root / "core" / "rules" / "engine.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("RuleType", engine_source)
        self.assertNotIn("current_price", engine_source)
        self.assertNotIn("availability", engine_source)
