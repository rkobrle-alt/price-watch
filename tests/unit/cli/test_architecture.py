"""Architecture boundary tests for the command-line application."""

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


def test_inner_packages_do_not_depend_on_cli() -> None:
    root = Path(__file__).parents[3]
    imports = {
        imported
        for package in (
            root / "core",
            root / "infrastructure",
            root / "applications" / "synchronization",
        )
        for module in package.rglob("*.py")
        for imported in _imports(module)
    }

    assert not any(name.startswith("applications.cli") for name in imports)


def test_cli_nondeterministic_process_reads_are_confined_to_main_adapter() -> None:
    root = Path(__file__).parents[3]
    package = root / "applications" / "cli"

    for module in package.glob("*.py"):
        if module.name == "main.py":
            continue
        source = module.read_text(encoding="utf-8")
        assert "datetime.now(" not in source
        assert "uuid4" not in source
        assert "sys.argv" not in source
        assert "sys.stdout" not in source
        assert "sys.stderr" not in source


def test_cli_contains_no_environment_or_float_configuration() -> None:
    root = Path(__file__).parents[3]
    package = root / "applications" / "cli"

    for module in package.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "os.environ" not in source
        assert "getenv(" not in source
        assert "float(" not in source


def test_command_handler_delegates_business_workflow() -> None:
    root = Path(__file__).parents[3]
    main_source = (
        root / "applications" / "cli" / "main.py"
    ).read_text(encoding="utf-8")

    assert "compose_sync(" in main_source
    assert "current_price" not in main_source
    assert "availability" not in main_source
    assert "StateSnapshot" not in main_source
