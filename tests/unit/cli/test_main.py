"""Tests for CLI dispatch, output and exit-code mapping."""

import importlib
from datetime import datetime
from typing import cast

import pytest

from applications.cli import run
from applications.cli.composition import SyncComposition
from applications.synchronization import SynchronizationResult
from core.notifications import NotificationError
from core.provider import ProviderError
from core.rules import RuleError
from core.state import StateStoreError
from tests.unit.cli.helpers import (
    RecordingStream,
    fixed_clock,
    fixed_notification_id,
)

main_module = importlib.import_module("applications.cli.main")


class ResultWorkflow:
    """Return or raise a configured synchronization outcome."""

    def __init__(self, outcome: SynchronizationResult | Exception) -> None:
        """Configure the workflow outcome."""
        self.outcome = outcome
        self.calls: list[tuple[object, datetime]] = []

    def run(self, rules: object, timestamp: datetime) -> SynchronizationResult:
        """Record the call and return or raise the configured outcome."""
        self.calls.append((rules, timestamp))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _result(*, errors: tuple[ProviderError, ...] = ()) -> SynchronizationResult:
    return SynchronizationResult((), (), (), (), errors)


def _sync_argv() -> tuple[str, ...]:
    return (
        "sync",
        "--url",
        "https://www.lidl.cz/tool/p100",
        "--state-file",
        "state.json",
    )


def _patch_composition(
    monkeypatch: pytest.MonkeyPatch,
    outcome: SynchronizationResult | Exception,
) -> ResultWorkflow:
    workflow = ResultWorkflow(outcome)
    composition = cast(SyncComposition, type("Composition", (), {
        "workflow": workflow,
        "rules": ("rule",),
    })())
    monkeypatch.setattr(main_module, "compose_sync", lambda *args: composition)
    return workflow


def test_version_writes_exact_output_and_returns_success() -> None:
    stdout = RecordingStream()
    stderr = RecordingStream()

    status = run(
        ("version",),
        stdout,
        stderr,
        fixed_clock,
        fixed_notification_id,
    )

    assert status == 0
    assert stdout.text() == "Price Watch 0.9.0\n"
    assert stdout.flush_count == 1
    assert stderr.text() == ""


@pytest.mark.parametrize(
    ("argument_name", "invalid_value"),
    [
        ("argv", "version"),
        ("argv", ("version", 1)),
        ("stdout", object()),
        ("stderr", object()),
        ("clock", 1),
        ("notification_id_factory", 1),
    ],
)
def test_run_rejects_invalid_public_dependencies(
    argument_name: str,
    invalid_value: object,
) -> None:
    arguments: dict[str, object] = {
        "argv": ("version",),
        "stdout": RecordingStream(),
        "stderr": RecordingStream(),
        "clock": fixed_clock,
        "notification_id_factory": fixed_notification_id,
    }
    arguments[argument_name] = invalid_value

    with pytest.raises(TypeError):
        run(**arguments)


@pytest.mark.parametrize(
    ("argv", "expected_status"),
    [
        ((), 2),
        (("--help",), 0),
    ],
)
def test_run_maps_parser_completion_to_status(
    argv: tuple[str, ...],
    expected_status: int,
) -> None:
    status = run(
        argv,
        RecordingStream(),
        RecordingStream(),
        fixed_clock,
        fixed_notification_id,
    )

    assert status == expected_status


def test_sync_success_writes_summary_and_uses_supplied_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = RecordingStream()
    stderr = RecordingStream()
    workflow = _patch_composition(monkeypatch, _result())

    status = run(
        _sync_argv(),
        stdout,
        stderr,
        fixed_clock,
        fixed_notification_id,
    )

    assert status == 0
    assert workflow.calls[0][0] == ("rule",)
    assert workflow.calls[0][1] == fixed_clock()
    assert stdout.text() == (
        "sync complete: products=0 evaluations=0 notifications=0 "
        "snapshots=0 provider_errors=0\n"
    )
    assert stdout.flush_count == 1
    assert stderr.text() == ""


def test_sync_provider_errors_are_written_and_return_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    errors = (ProviderError("first"), ProviderError("second"))
    stdout = RecordingStream()
    stderr = RecordingStream()
    _patch_composition(monkeypatch, _result(errors=errors))

    status = run(
        _sync_argv(),
        stdout,
        stderr,
        fixed_clock,
        fixed_notification_id,
    )

    assert status == 1
    assert stderr.text() == (
        "provider error: first\n"
        "provider error: second\n"
    )
    assert stderr.flush_count == 2
    assert "provider_errors=2" in stdout.text()


def test_invalid_composition_value_returns_usage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = ValueError("invalid URL")
    monkeypatch.setattr(
        main_module,
        "compose_sync",
        lambda *args: (_ for _ in ()).throw(failure),
    )
    stderr = RecordingStream()

    status = run(
        _sync_argv(),
        RecordingStream(),
        stderr,
        fixed_clock,
        fixed_notification_id,
    )

    assert status == 2
    assert stderr.text() == "error: invalid URL\n"


@pytest.mark.parametrize(
    "failure",
    [
        StateStoreError("state failed"),
        RuleError("rule failed"),
        NotificationError("notification failed"),
    ],
)
def test_known_operational_failure_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    _patch_composition(monkeypatch, failure)
    stderr = RecordingStream()

    status = run(
        _sync_argv(),
        RecordingStream(),
        stderr,
        fixed_clock,
        fixed_notification_id,
    )

    assert status == 1
    assert stderr.text() == f"error: {failure}\n"


@pytest.mark.parametrize(
    "stage",
    ["composition", "clock", "identifier", "workflow"],
)
def test_unexpected_failures_propagate(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    failure = RuntimeError(f"{stage} failed")
    clock = fixed_clock
    notification_id_factory = fixed_notification_id
    if stage == "composition":
        monkeypatch.setattr(
            main_module,
            "compose_sync",
            lambda *args: (_ for _ in ()).throw(failure),
        )
    elif stage == "identifier":
        notification_id_factory = lambda: (_ for _ in ()).throw(failure)
        monkeypatch.setattr(
            main_module,
            "compose_sync",
            lambda arguments, stdout, supplied_clock, factory: factory(),
        )
    else:
        _patch_composition(monkeypatch, failure)
    if stage == "clock":
        clock = lambda: (_ for _ in ()).throw(failure)

    with pytest.raises(RuntimeError) as captured:
        run(
            _sync_argv(),
            RecordingStream(),
            RecordingStream(),
            clock,
            notification_id_factory,
        )

    assert captured.value is failure
