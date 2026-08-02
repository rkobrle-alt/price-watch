"""Tests for the Home Assistant App process boundary."""

import importlib
from datetime import timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from applications.homeassistant.composition import _HomeAssistantComposition
from applications.homeassistant.main import run
from applications.synchronization import SynchronizationResult, SynchronizationWorkflow
from core.notifications import NotificationError
from core.provider import FetchResult, ProviderError
from core.rules import RuleError
from core.scheduler import SchedulerError
from core.state import StateStoreError
from tests.unit.homeassistant_app.helpers import (
    TIMESTAMP,
    RecordingDelay,
    RecordingStream,
    create_options,
)
from tests.unit.notifications.helpers import create_product

app_main = importlib.import_module("applications.homeassistant.main")


class FakeWorkflow:
    """Return configured cycle results or raise a failure."""

    def __init__(
        self,
        results: tuple[SynchronizationResult, ...] = (),
        failure: BaseException | None = None,
    ) -> None:
        """Configure results and optional failure."""
        self.results = results
        self.failure = failure
        self.calls = 0

    def run(self, rules: object, timestamp: object) -> SynchronizationResult:
        """Record the call and return the next result."""
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def _result(
    *,
    provider_error: bool = False,
    product: bool = False,
) -> SynchronizationResult:
    errors = (ProviderError("Lidl failed"),) if provider_error else ()
    fetch_results: tuple[FetchResult, ...] = ()
    if product:
        fetch_results = (
            FetchResult(
                products=(create_product(),),
                started_at=TIMESTAMP,
                finished_at=TIMESTAMP,
                duration=timedelta(0),
                errors=(),
            ),
        )
    return SynchronizationResult(
        fetch_results=fetch_results,
        evaluations=(),
        notifications=(),
        snapshots=(),
        provider_errors=errors,
    )


def _composition(workflow: FakeWorkflow) -> _HomeAssistantComposition:
    return _HomeAssistantComposition(
        cast(SynchronizationWorkflow, workflow),
        (),
        timedelta(seconds=300),
    )


def _run_with_workflow(
    monkeypatch: pytest.MonkeyPatch,
    workflow: FakeWorkflow,
    *,
    delay: RecordingDelay | None = None,
    max_cycles: int = 1,
) -> tuple[int, RecordingStream, RecordingStream, RecordingDelay]:
    monkeypatch.setattr(
        app_main,
        "_compose_homeassistant",
        lambda *arguments: _composition(workflow),
    )
    stdout = RecordingStream()
    stderr = RecordingStream()
    actual_delay = delay or RecordingDelay()
    status = run(
        create_options(),
        "injected-token",
        stdout,
        stderr,
        lambda: TIMESTAMP,
        uuid4,
        actual_delay,
        data_directory=Path("/data"),
        max_cycles=max_cycles,
    )
    return status, stdout, stderr, actual_delay


def test_run_executes_immediately_then_at_fixed_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = FakeWorkflow((_result(product=True), _result()))

    status, stdout, stderr, delay = _run_with_workflow(
        monkeypatch,
        workflow,
        max_cycles=2,
    )

    assert status == 0
    assert workflow.calls == 2
    assert delay.durations == [timedelta(seconds=300)]
    assert stdout.text.count("sync complete:") == 2
    assert "products=1" in stdout.text
    assert stdout.text.endswith("watch complete: cycles=2 provider_error_cycles=0\n")
    assert stderr.text == ""


def test_provider_error_cycles_continue_and_return_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = FakeWorkflow((_result(provider_error=True), _result()))

    status, stdout, stderr, delay = _run_with_workflow(
        monkeypatch,
        workflow,
        max_cycles=2,
    )

    assert status == 1
    assert workflow.calls == 2
    assert len(delay.durations) == 1
    assert "provider error: Lidl failed" in stderr.text
    assert "provider_error_cycles=1" in stdout.text


@pytest.mark.parametrize(
    "failure",
    [
        StateStoreError("state failed"),
        RuleError("rule failed"),
        NotificationError("delivery failed"),
        SchedulerError("delay failed"),
    ],
)
def test_run_maps_known_operational_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    status, stdout, stderr, delay = _run_with_workflow(
        monkeypatch,
        FakeWorkflow(failure=failure),
    )

    assert status == 1
    assert stdout.text == ""
    assert stderr.text == f"error: {failure}\n"
    assert delay.durations == []


def test_run_maps_interruption_after_completed_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delay = RecordingDelay(failure=KeyboardInterrupt())

    status, stdout, stderr, _ = _run_with_workflow(
        monkeypatch,
        FakeWorkflow((_result(),)),
        delay=delay,
        max_cycles=2,
    )

    assert status == 130
    assert stdout.text.endswith("watch stopped: cycles=1 provider_error_cycles=0\n")
    assert stderr.text == ""


def test_run_propagates_unexpected_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    failure = RuntimeError("bug")

    with pytest.raises(RuntimeError) as captured:
        _run_with_workflow(monkeypatch, FakeWorkflow(failure=failure))

    assert captured.value is failure


def test_run_reports_blank_token_without_composition() -> None:
    stderr = RecordingStream()

    status = run(
        create_options(),
        " ",
        RecordingStream(),
        stderr,
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
    )

    assert status == 2
    assert stderr.text == "error: SUPERVISOR_TOKEN cannot be blank\n"


def test_run_maps_option_and_composition_configuration_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = RecordingStream()
    stderr = RecordingStream()
    status = run(
        {},
        "token",
        stdout,
        stderr,
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        max_cycles=1,
    )
    assert status == 2
    assert "missing keys" in stderr.text

    monkeypatch.setattr(
        app_main,
        "_compose_homeassistant",
        lambda *arguments: (_ for _ in ()).throw(ValueError("bad URL")),
    )
    stderr = RecordingStream()
    status = run(
        create_options(),
        "token",
        stdout,
        stderr,
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        max_cycles=1,
    )
    assert status == 2
    assert stderr.text == "error: bad URL\n"


@pytest.mark.parametrize(
    ("field", "value", "exception_type", "message"),
    [
        ("options", [], TypeError, "options"),
        ("access_token", 1, TypeError, "access_token"),
        ("stdout", object(), TypeError, "stdout"),
        ("stderr", object(), TypeError, "stderr"),
        ("clock", object(), TypeError, "clock"),
        ("notification_id_factory", object(), TypeError, "notification_id_factory"),
        ("delay", object(), TypeError, "delay"),
        ("data_directory", "data", TypeError, "data_directory"),
        ("max_cycles", True, TypeError, "max_cycles"),
        ("max_cycles", 0, ValueError, "max_cycles"),
    ],
)
def test_run_rejects_invalid_public_dependencies(
    field: str,
    value: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "options": create_options(),
        "access_token": "token",
        "stdout": RecordingStream(),
        "stderr": RecordingStream(),
        "clock": lambda: TIMESTAMP,
        "notification_id_factory": uuid4,
        "delay": RecordingDelay(),
        "data_directory": Path("/data"),
        "max_cycles": 1,
    }
    values[field] = value

    with pytest.raises(exception_type, match=message):
        run(**values)
