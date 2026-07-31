"""Tests for CLI configuration-file modes and resolution."""

import importlib
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest

from applications.cli import run
from applications.cli.arguments import (
    SyncArguments,
    SyncConfigurationArguments,
    WatchArguments,
    WatchConfigurationArguments,
)
from applications.cli.composition import SyncComposition
from applications.cli.configuration import resolve_configured_command
from applications.cli.parser import ParserExit, parse_arguments
from applications.synchronization import SynchronizationResult
from core.configuration import ConfigurationError
from tests.unit.cli.helpers import (
    RecordingStream,
    fixed_clock,
    fixed_notification_id,
)

main_module = importlib.import_module("applications.cli.main")


class FakeLoader:
    """Return or raise a configured loading outcome."""

    def __init__(self, outcome: Mapping[str, object] | BaseException) -> None:
        """Configure the outcome."""
        self.outcome = outcome
        self.paths: list[Path] = []

    def load(self, path: Path) -> Mapping[str, object]:
        """Record the path and return or raise the outcome."""
        self.paths.append(path)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class RecordingDelay:
    """Record configured watch intervals."""

    def __init__(self) -> None:
        """Create an empty duration record."""
        self.durations: list[timedelta] = []

    def wait(self, duration: timedelta) -> None:
        """Record one duration."""
        self.durations.append(duration)


class ResultWorkflow:
    """Return one empty result for every cycle."""

    def __init__(self) -> None:
        """Create an empty call record."""
        self.calls = 0

    def run(self, rules: object, timestamp: object) -> SynchronizationResult:
        """Record and return an empty synchronization result."""
        self.calls += 1
        return SynchronizationResult((), (), (), (), ())


def _document(*, scheduler: bool = True) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "provider": {
            "lidl": {
                "product_urls": ["https://www.lidl.cz/tool/p100"],
            }
        },
        "state": {"file": "data/state.json"},
    }
    if scheduler:
        document["scheduler"] = {"interval_seconds": 5}
    return document


def _patch_composition(monkeypatch: pytest.MonkeyPatch) -> ResultWorkflow:
    workflow = ResultWorkflow()
    composition = cast(
        SyncComposition,
        type("Composition", (), {"workflow": workflow, "rules": ()})(),
    )
    monkeypatch.setattr(main_module, "compose_sync", lambda *args: composition)
    return workflow


def test_configuration_command_values_are_immutable() -> None:
    sync = SyncConfigurationArguments(Path("config.toml"))
    watch = WatchConfigurationArguments(Path("config.toml"), 2)

    assert watch.max_cycles == 2
    with pytest.raises(FrozenInstanceError):
        sync.config_file = Path("other.toml")


@pytest.mark.parametrize(
    ("factory", "arguments", "exception_type"),
    [
        (SyncConfigurationArguments, ("config.toml",), TypeError),
        (WatchConfigurationArguments, ("config.toml", None), TypeError),
        (WatchConfigurationArguments, (Path("config.toml"), True), TypeError),
        (WatchConfigurationArguments, (Path("config.toml"), "2"), TypeError),
        (WatchConfigurationArguments, (Path("config.toml"), 0), ValueError),
    ],
)
def test_configuration_command_values_reject_invalid_fields(
    factory: object,
    arguments: tuple[object, ...],
    exception_type: type[Exception],
) -> None:
    with pytest.raises(exception_type):
        cast(object, factory)(*arguments)


def test_parser_creates_configured_sync_command() -> None:
    command = parse_arguments(
        ("sync", "--config", "config/price-watch.toml"),
        RecordingStream(),
        RecordingStream(),
    )

    assert command == SyncConfigurationArguments(Path("config/price-watch.toml"))


def test_parser_creates_bounded_configured_watch_command() -> None:
    command = parse_arguments(
        ("watch", "--config", "config.toml", "--max-cycles", "3"),
        RecordingStream(),
        RecordingStream(),
    )

    assert command == WatchConfigurationArguments(Path("config.toml"), 3)


@pytest.mark.parametrize(
    "direct_option",
    [
        ("--url", "https://www.lidl.cz/tool/p100"),
        ("--state-file", "state.json"),
        ("--timeout-seconds", "10"),
        ("--price-drop-percentage", "10"),
        ("--price-drop-amount", "20"),
        ("--interval-seconds", "5"),
    ],
)
def test_watch_config_rejects_every_direct_configuration_option(
    direct_option: tuple[str, str],
) -> None:
    stderr = RecordingStream()

    with pytest.raises(ParserExit) as captured:
        parse_arguments(
            ("watch", "--config", "config.toml", *direct_option),
            RecordingStream(),
            stderr,
        )

    assert captured.value.status == 2
    assert "cannot be combined" in stderr.text()


@pytest.mark.parametrize(
    "direct_option",
    [
        ("--url", "https://www.lidl.cz/tool/p100"),
        ("--state-file", "state.json"),
        ("--timeout-seconds", "10"),
        ("--price-drop-percentage", "10"),
        ("--price-drop-amount", "20"),
    ],
)
def test_sync_config_rejects_direct_configuration_option(
    direct_option: tuple[str, str],
) -> None:
    with pytest.raises(ParserExit) as captured:
        parse_arguments(
            ("sync", "--config", "config.toml", *direct_option),
            RecordingStream(),
            RecordingStream(),
        )

    assert captured.value.status == 2


def test_resolver_builds_existing_sync_arguments_relative_to_config() -> None:
    loader = FakeLoader(_document())
    command = SyncConfigurationArguments(Path("settings/price-watch.toml"))

    resolved = resolve_configured_command(command, loader)

    assert resolved == SyncArguments(
        product_urls=("https://www.lidl.cz/tool/p100",),
        state_file=Path("settings/data/state.json"),
    )
    assert loader.paths == [command.config_file]


def test_resolver_builds_existing_bounded_watch_arguments() -> None:
    resolved = resolve_configured_command(
        WatchConfigurationArguments(Path("config.toml"), 2),
        FakeLoader(_document()),
    )

    assert isinstance(resolved, WatchArguments)
    assert resolved.interval == timedelta(seconds=5)
    assert resolved.max_cycles == 2


def test_resolver_requires_scheduler_for_watch() -> None:
    with pytest.raises(ConfigurationError, match="required for watch"):
        resolve_configured_command(
            WatchConfigurationArguments(Path("config.toml")),
            FakeLoader(_document(scheduler=False)),
        )


@pytest.mark.parametrize(
    ("command", "loader"),
    [
        (cast(SyncConfigurationArguments, object()), FakeLoader(_document())),
        (SyncConfigurationArguments(Path("config.toml")), object()),
    ],
)
def test_resolver_rejects_invalid_public_dependencies(
    command: SyncConfigurationArguments,
    loader: object,
) -> None:
    with pytest.raises(TypeError):
        resolve_configured_command(command, cast(object, loader))


def test_configured_sync_uses_existing_composition_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _patch_composition(monkeypatch)
    loader = FakeLoader(_document())
    stdout = RecordingStream()

    status = run(
        ("sync", "--config", "config.toml"),
        stdout,
        RecordingStream(),
        fixed_clock,
        fixed_notification_id,
        configuration_loader=loader,
    )

    assert status == 0
    assert workflow.calls == 1
    assert "sync complete:" in stdout.text()


def test_configured_watch_uses_existing_scheduler_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _patch_composition(monkeypatch)
    delay = RecordingDelay()

    status = run(
        ("watch", "--config", "config.toml", "--max-cycles", "2"),
        RecordingStream(),
        RecordingStream(),
        fixed_clock,
        fixed_notification_id,
        delay=delay,
        configuration_loader=FakeLoader(_document()),
    )

    assert status == 0
    assert workflow.calls == 2
    assert delay.durations == [timedelta(seconds=5)]


def test_configured_command_requires_injected_loader() -> None:
    with pytest.raises(TypeError, match="configuration_loader is required"):
        run(
            ("sync", "--config", "config.toml"),
            RecordingStream(),
            RecordingStream(),
            fixed_clock,
            fixed_notification_id,
        )


def test_run_rejects_invalid_optional_loader() -> None:
    with pytest.raises(TypeError, match="configuration_loader must expose"):
        run(
            ("version",),
            RecordingStream(),
            RecordingStream(),
            fixed_clock,
            fixed_notification_id,
            configuration_loader=cast(object, object()),
        )


def test_configuration_error_returns_usage_failure() -> None:
    failure = ConfigurationError("invalid configuration")
    stderr = RecordingStream()

    status = run(
        ("sync", "--config", "config.toml"),
        RecordingStream(),
        stderr,
        fixed_clock,
        fixed_notification_id,
        configuration_loader=FakeLoader(failure),
    )

    assert status == 2
    assert stderr.text() == "error: invalid configuration\n"


def test_unexpected_loader_failure_propagates() -> None:
    failure = RuntimeError("bug")

    with pytest.raises(RuntimeError) as captured:
        run(
            ("sync", "--config", "config.toml"),
            RecordingStream(),
            RecordingStream(),
            fixed_clock,
            fixed_notification_id,
            configuration_loader=FakeLoader(failure),
        )

    assert captured.value is failure
