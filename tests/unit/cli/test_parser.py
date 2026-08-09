"""Tests for CLI parsing and diagnostics."""

from decimal import Decimal
from pathlib import Path

import pytest

from applications.cli.arguments import (
    MaintenanceArguments,
    SyncArguments,
    VersionArguments,
)
from applications.cli.parser import ParserExit, _create_parser, parse_arguments
from tests.unit.cli.helpers import RecordingStream


def test_version_command_parses_without_options() -> None:
    command = parse_arguments(("version",), RecordingStream(), RecordingStream())

    assert isinstance(command, VersionArguments)


def test_sync_command_parses_defaults_order_and_exact_decimals() -> None:
    stdout = RecordingStream()
    stderr = RecordingStream()

    command = parse_arguments(
        (
            "sync",
            "--url",
            "https://www.lidl.cz/first/p100",
            "--url",
            "https://www.lidl.cz/first/p100",
            "--state-file",
            "data/state.json",
            "--timeout-seconds",
            "25",
            "--price-drop-percentage",
            "10.50",
            "--price-drop-amount",
            "250.00",
        ),
        stdout,
        stderr,
    )

    assert command == SyncArguments(
        product_urls=(
            "https://www.lidl.cz/first/p100",
            "https://www.lidl.cz/first/p100",
        ),
        state_file=Path("data/state.json"),
        timeout_seconds=25,
        price_drop_percentage=Decimal("10.50"),
        price_drop_amount=Decimal("250.00"),
    )
    assert stdout.text() == ""
    assert stderr.text() == ""


def test_sync_command_uses_optional_defaults() -> None:
    command = parse_arguments(
        (
            "sync",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
        ),
        RecordingStream(),
        RecordingStream(),
    )

    assert isinstance(command, SyncArguments)
    assert command.timeout_seconds == 10
    assert command.price_drop_percentage is None
    assert command.price_drop_amount is None


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (
            (
                "maintenance",
                "--database-file",
                "catalog.sqlite3",
                "--retention-days",
                "90",
            ),
            MaintenanceArguments(Path("catalog.sqlite3"), 90),
        ),
        (
            (
                "maintenance",
                "--database-file",
                "catalog.sqlite3",
                "--retention-days",
                "30",
                "--apply",
                "--backup-file",
                "backup.sqlite3",
            ),
            MaintenanceArguments(
                Path("catalog.sqlite3"),
                30,
                True,
                Path("backup.sqlite3"),
            ),
        ),
    ],
)
def test_maintenance_command_parses_plan_and_apply(
    argv: tuple[str, ...],
    expected: MaintenanceArguments,
) -> None:
    assert parse_arguments(argv, RecordingStream(), RecordingStream()) == expected


@pytest.mark.parametrize(
    "argv",
    [
        (),
        ("unknown",),
        ("sync", "--state-file", "state.json"),
        ("sync", "--url", "https://www.lidl.cz/tool/p100"),
        ("maintenance", "--retention-days", "90"),
        ("maintenance", "--database-file", "catalog.sqlite3"),
        (
            "maintenance",
            "--database-file",
            "catalog.sqlite3",
            "--retention-days",
            "0",
        ),
        (
            "maintenance",
            "--database-file",
            "catalog.sqlite3",
            "--retention-days",
            "90",
            "--apply",
        ),
        (
            "maintenance",
            "--database-file",
            "catalog.sqlite3",
            "--retention-days",
            "90",
            "--backup-file",
            "backup.sqlite3",
        ),
        (
            "sync",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
            "--timeout-seconds",
            "invalid",
        ),
        (
            "sync",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
            "--timeout-seconds",
            "0",
        ),
        (
            "sync",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
            "--price-drop-percentage",
            "invalid",
        ),
        (
            "sync",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
            "--price-drop-percentage",
            "NaN",
        ),
        (
            "sync",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
            "--price-drop-percentage",
            "-1",
        ),
        (
            "sync",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
            "--price-drop-percentage",
            "101",
        ),
        (
            "sync",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
            "--price-drop-amount",
            "NaN",
        ),
        (
            "sync",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
            "--price-drop-amount",
            "-1",
        ),
    ],
)
def test_parser_errors_use_injected_stderr(argv: tuple[str, ...]) -> None:
    stdout = RecordingStream()
    stderr = RecordingStream()

    with pytest.raises(ParserExit) as captured:
        parse_arguments(argv, stdout, stderr)

    assert captured.value.status == 2
    assert "error:" in stderr.text()
    assert stderr.flush_count >= 1
    assert stdout.text() == ""


@pytest.mark.parametrize(
    "argv",
    [("--help",), ("sync", "--help"), ("maintenance", "--help")],
)
def test_help_uses_injected_stdout(argv: tuple[str, ...]) -> None:
    stdout = RecordingStream()
    stderr = RecordingStream()

    with pytest.raises(ParserExit) as captured:
        parse_arguments(argv, stdout, stderr)

    assert captured.value.status == 0
    assert "usage:" in stdout.text()
    assert stderr.text() == ""


def test_parser_stream_overrides_and_exit_messages() -> None:
    stdout = RecordingStream()
    stderr = RecordingStream()
    alternate = RecordingStream()
    parser = _create_parser(stdout, stderr)

    parser.print_help(alternate)
    parser.print_usage(alternate)
    with pytest.raises(ParserExit) as success:
        parser.exit(0, "done\n")
    with pytest.raises(ParserExit) as failure:
        parser.exit(1, "failed\n")

    assert "usage:" in alternate.text()
    assert success.value.status == 0
    assert failure.value.status == 1
    assert stdout.text().endswith("done\n")
    assert stderr.text() == "failed\n"
