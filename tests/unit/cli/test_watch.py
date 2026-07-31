"""Tests for CLI interval scheduling."""

import importlib
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from applications.cli import run
from applications.cli.arguments import SyncArguments, WatchArguments
from applications.cli.composition import SyncComposition
from applications.cli.parser import ParserExit, parse_arguments
from applications.synchronization import SynchronizationResult
from core.provider import ProviderError
from core.scheduler import SchedulerError
from core.state import StateStoreError
from tests.unit.cli.helpers import (
    RecordingStream,
    fixed_clock,
    fixed_notification_id,
)

main_module = importlib.import_module("applications.cli.main")


class RecordingDelay:
    """Record waits and optionally interrupt or fail."""

    def __init__(self, failure: BaseException | None = None) -> None:
        """Configure an optional failure."""
        self.durations: list[timedelta] = []
        self.failure = failure

    def wait(self, duration: timedelta) -> None:
        """Record one duration and raise the configured failure."""
        self.durations.append(duration)
        if self.failure is not None:
            raise self.failure


class SequenceWorkflow:
    """Return configured outcomes in call order."""

    def __init__(
        self,
        outcomes: list[SynchronizationResult | BaseException],
    ) -> None:
        """Configure sequential outcomes."""
        self.outcomes = outcomes
        self.calls: list[tuple[object, datetime]] = []

    def run(self, rules: object, timestamp: datetime) -> SynchronizationResult:
        """Record the call, then return or raise the next outcome."""
        self.calls.append((rules, timestamp))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _sync_arguments() -> SyncArguments:
    return SyncArguments(
        product_urls=("https://www.lidl.cz/tool/p100",),
        state_file=Path("state.json"),
    )


def _watch_argv(*extra: str) -> tuple[str, ...]:
    return (
        "watch",
        "--url",
        "https://www.lidl.cz/tool/p100",
        "--state-file",
        "state.json",
        "--interval-seconds",
        "5",
        *extra,
    )


def _result(*, provider_error: bool = False) -> SynchronizationResult:
    errors = (ProviderError("temporary"),) if provider_error else ()
    return SynchronizationResult((), (), (), (), errors)


def _patch_composition(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[SynchronizationResult | BaseException],
) -> SequenceWorkflow:
    workflow = SequenceWorkflow(outcomes)
    composition = cast(
        SyncComposition,
        type("Composition", (), {"workflow": workflow, "rules": ("rule",)})(),
    )
    monkeypatch.setattr(main_module, "compose_sync", lambda *args: composition)
    return workflow


def test_watch_arguments_are_immutable_and_retain_values() -> None:
    arguments = WatchArguments(_sync_arguments(), timedelta(seconds=5), 3)

    assert arguments.interval == timedelta(seconds=5)
    assert arguments.max_cycles == 3
    with pytest.raises(FrozenInstanceError):
        arguments.max_cycles = 4


@pytest.mark.parametrize(
    ("overrides", "exception_type"),
    [
        ({"sync": cast(SyncArguments, object())}, TypeError),
        ({"interval": cast(timedelta, 5)}, TypeError),
        ({"interval": timedelta(0)}, ValueError),
        ({"interval": timedelta(seconds=-1)}, ValueError),
        ({"max_cycles": True}, TypeError),
        ({"max_cycles": cast(int, "2")}, TypeError),
        ({"max_cycles": 0}, ValueError),
        ({"max_cycles": -1}, ValueError),
    ],
)
def test_watch_arguments_reject_invalid_values(
    overrides: dict[str, object],
    exception_type: type[Exception],
) -> None:
    values: dict[str, object] = {
        "sync": _sync_arguments(),
        "interval": timedelta(seconds=5),
        "max_cycles": None,
    }
    values.update(overrides)

    with pytest.raises(exception_type):
        WatchArguments(**values)


def test_watch_parser_reuses_sync_options_and_scheduler_defaults() -> None:
    command = parse_arguments(
        _watch_argv(
            "--timeout-seconds",
            "12",
            "--price-drop-percentage",
            "10.50",
            "--price-drop-amount",
            "20.00",
        ),
        RecordingStream(),
        RecordingStream(),
    )

    assert isinstance(command, WatchArguments)
    assert command.sync.timeout_seconds == 12
    assert str(command.sync.price_drop_percentage) == "10.50"
    assert str(command.sync.price_drop_amount) == "20.00"
    assert command.interval == timedelta(seconds=5)
    assert command.max_cycles is None


def test_watch_parser_accepts_finite_cycle_limit() -> None:
    command = parse_arguments(
        _watch_argv("--max-cycles", "3"),
        RecordingStream(),
        RecordingStream(),
    )

    assert isinstance(command, WatchArguments)
    assert command.max_cycles == 3


@pytest.mark.parametrize(
    "argv",
    [
        (
            "watch",
            "--url",
            "https://www.lidl.cz/tool/p100",
            "--state-file",
            "state.json",
        ),
        _watch_argv("--max-cycles", "0"),
    ],
)
def test_watch_parser_rejects_invalid_schedule(argv: tuple[str, ...]) -> None:
    stderr = RecordingStream()

    with pytest.raises(ParserExit) as captured:
        parse_arguments(argv, RecordingStream(), stderr)

    assert captured.value.status == 2
    assert "error:" in stderr.text()


def test_watch_help_uses_injected_stdout() -> None:
    stdout = RecordingStream()

    with pytest.raises(ParserExit) as captured:
        parse_arguments(("watch", "--help"), stdout, RecordingStream())

    assert captured.value.status == 0
    assert "--interval-seconds" in stdout.text()


def test_finite_watch_uses_fresh_timestamps_and_exact_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    second = datetime(2026, 8, 1, 12, 1, tzinfo=UTC)
    timestamps = iter((first, second))
    workflow = _patch_composition(monkeypatch, [_result(), _result()])
    delay = RecordingDelay()
    stdout = RecordingStream()

    status = run(
        _watch_argv("--max-cycles", "2"),
        stdout,
        RecordingStream(),
        lambda: next(timestamps),
        fixed_notification_id,
        delay=delay,
    )

    assert status == 0
    assert [call[1] for call in workflow.calls] == [first, second]
    assert delay.durations == [timedelta(seconds=5)]
    assert stdout.text().count("sync complete:") == 2
    assert stdout.text().endswith(
        "watch complete: cycles=2 provider_error_cycles=0\n"
    )


def test_provider_error_cycle_does_not_stop_watch_and_returns_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _patch_composition(
        monkeypatch,
        [_result(provider_error=True), _result()],
    )
    stdout = RecordingStream()
    stderr = RecordingStream()

    status = run(
        _watch_argv("--max-cycles", "2"),
        stdout,
        stderr,
        fixed_clock,
        fixed_notification_id,
        delay=RecordingDelay(),
    )

    assert status == 1
    assert len(workflow.calls) == 2
    assert stderr.text() == "provider error: temporary\n"
    assert stdout.text().endswith(
        "watch complete: cycles=2 provider_error_cycles=1\n"
    )


def test_watch_requires_injected_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_composition(monkeypatch, [_result()])

    with pytest.raises(TypeError, match="delay is required"):
        run(
            _watch_argv("--max-cycles", "1"),
            RecordingStream(),
            RecordingStream(),
            fixed_clock,
            fixed_notification_id,
        )


def test_run_rejects_invalid_optional_delay() -> None:
    with pytest.raises(TypeError, match="delay must expose"):
        run(
            ("version",),
            RecordingStream(),
            RecordingStream(),
            fixed_clock,
            fixed_notification_id,
            delay=cast(object, object()),
        )


@pytest.mark.parametrize(
    "failure",
    [StateStoreError("state failed"), SchedulerError("delay failed")],
)
def test_watch_maps_known_failure_to_one(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    delay = RecordingDelay(failure) if isinstance(failure, SchedulerError) else RecordingDelay()
    outcomes: list[SynchronizationResult | BaseException] = (
        [_result(), _result()]
        if isinstance(failure, SchedulerError)
        else [failure]
    )
    _patch_composition(monkeypatch, outcomes)
    stderr = RecordingStream()

    status = run(
        _watch_argv("--max-cycles", "2"),
        RecordingStream(),
        stderr,
        fixed_clock,
        fixed_notification_id,
        delay=delay,
    )

    assert status == 1
    assert stderr.text() == f"error: {failure}\n"


@pytest.mark.parametrize("during_cycle", [False, True])
def test_keyboard_interrupt_stops_watch_with_completed_count(
    monkeypatch: pytest.MonkeyPatch,
    during_cycle: bool,
) -> None:
    interruption = KeyboardInterrupt()
    outcomes: list[SynchronizationResult | BaseException] = (
        [interruption] if during_cycle else [_result(), _result()]
    )
    delay = RecordingDelay(None if during_cycle else interruption)
    _patch_composition(monkeypatch, outcomes)
    stdout = RecordingStream()

    status = run(
        _watch_argv(),
        stdout,
        RecordingStream(),
        fixed_clock,
        fixed_notification_id,
        delay=delay,
    )

    assert status == 130
    expected_cycles = 0 if during_cycle else 1
    assert stdout.text().endswith(
        f"watch stopped: cycles={expected_cycles} provider_error_cycles=0\n"
    )


def test_unexpected_watch_failure_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("bug")
    _patch_composition(monkeypatch, [_result(), _result()])

    with pytest.raises(RuntimeError) as captured:
        run(
            _watch_argv(),
            RecordingStream(),
            RecordingStream(),
            fixed_clock,
            fixed_notification_id,
            delay=RecordingDelay(failure),
        )

    assert captured.value is failure
