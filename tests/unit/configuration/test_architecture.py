"""Architecture tests for configuration side-effect boundaries."""

from pathlib import Path


def test_core_and_application_configuration_perform_no_file_io() -> None:
    root = Path(__file__).parents[3]

    for package in (
        root / "core" / "configuration",
        root / "applications" / "configuration",
    ):
        for module in package.rglob("*.py"):
            source = module.read_text(encoding="utf-8")
            assert "read_text(" not in source
            assert "read_bytes(" not in source
            assert "tomllib" not in source


def test_configuration_contains_no_environment_or_business_subsystems() -> None:
    root = Path(__file__).parents[3]

    for package in (
        root / "core" / "configuration",
        root / "applications" / "configuration",
        root / "infrastructure" / "configuration",
    ):
        for module in package.rglob("*.py"):
            source = module.read_text(encoding="utf-8")
            assert "os.environ" not in source
            assert "getenv(" not in source
            assert "core.rules" not in source
            assert "core.provider" not in source
            assert "core.notifications" not in source
            assert "core.state" not in source
