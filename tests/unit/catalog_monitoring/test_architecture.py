"""Architecture boundary tests for catalog monitoring Applications."""

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def test_catalog_monitoring_has_no_infrastructure_or_outer_application_imports() -> None:
    root = Path(__file__).parents[3]
    package = root / "applications" / "catalog_monitoring"
    imports = {
        imported
        for module in package.glob("*.py")
        for imported in _imports(module)
    }

    assert not any(name.startswith("infrastructure") for name in imports)
    assert not any(name.startswith("applications.cli") for name in imports)
    assert not any(name.startswith("applications.homeassistant") for name in imports)


def test_catalog_monitoring_has_no_hidden_time_randomness_or_io() -> None:
    root = Path(__file__).parents[3]
    package = root / "applications" / "catalog_monitoring"

    for module in package.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "datetime.now(" not in source
        assert "datetime.utcnow(" not in source
        assert "uuid4(" not in source
        assert "os.environ" not in source
        assert "getenv(" not in source
        assert "open(" not in source
