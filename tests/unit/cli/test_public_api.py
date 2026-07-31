"""Public API and project metadata tests for the CLI."""

import inspect
from pathlib import Path

import applications.cli as cli_api
from applications.cli import VERSION, main, run


def test_cli_public_api_is_explicit_and_documented() -> None:
    assert cli_api.__all__ == ["VERSION", "main", "run"]
    assert cli_api.VERSION is VERSION
    assert cli_api.main is main
    assert cli_api.run is run
    assert inspect.getdoc(main)
    assert inspect.getdoc(run)
    assert inspect.signature(main).return_annotation is int
    assert inspect.signature(run).return_annotation is int


def test_version_and_console_script_match_project_metadata() -> None:
    root = Path(__file__).parents[3]
    metadata = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert f'version = "{VERSION}"' in metadata
    assert 'price-watch = "applications.cli:main"' in metadata
