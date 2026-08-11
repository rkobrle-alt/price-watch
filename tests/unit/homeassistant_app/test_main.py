"""Tests for the Home Assistant App process boundary."""

import importlib
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from applications.homeassistant.composition import _HomeAssistantComposition
from applications.homeassistant.lifecycle import _TerminationRequested
from applications.homeassistant.main import run
from applications.synchronization import SynchronizationResult, SynchronizationWorkflow
from core.domain import Product
from core.notifications import (
    DailyDigestReservationError,
    NotificationError,
    NotificationReservationError,
)
from core.provider import FetchResult, ProviderError
from core.rules import RuleError
from core.scheduler import SchedulerError
from core.state import StateStoreError
from infrastructure.homeassistant import (
    HomeAssistantError,
    HomeAssistantStatusPublisher,
)
from infrastructure.persistence.migration import ZipMigrationArchive
from tests.unit.homeassistant_app.helpers import (
    TIMESTAMP,
    RecordingDelay,
    RecordingStream,
    create_options,
)
from tests.unit.notifications.helpers import create_product

app_main = importlib.import_module("applications.homeassistant.main")


class FakeStatusPublisher:
    """Capture status publications or raise a configured failure."""

    def __init__(self, failure: BaseException | None = None) -> None:
        """Configure optional publication failure."""
        self.failure = failure
        self.calls: list[tuple[tuple[Product, ...], datetime, int, int]] = []

    def publish_cycle(
        self,
        products: tuple[Product, ...],
        timestamp: datetime,
        notification_count: int,
        provider_error_count: int,
    ) -> None:
        """Record the call before raising an optional failure."""
        self.calls.append(
            (products, timestamp, notification_count, provider_error_count)
        )
        if self.failure is not None:
            raise self.failure


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


def _composition(
    workflow: FakeWorkflow,
    status_publisher: FakeStatusPublisher | None = None,
) -> _HomeAssistantComposition:
    publisher = status_publisher or FakeStatusPublisher()
    return _HomeAssistantComposition(
        workflow=cast(SynchronizationWorkflow, workflow),
        status_publisher=cast(HomeAssistantStatusPublisher, publisher),
        rules=(),
        interval=timedelta(seconds=300),
    )


def _run_with_workflow(
    monkeypatch: pytest.MonkeyPatch,
    workflow: FakeWorkflow,
    *,
    delay: RecordingDelay | None = None,
    max_cycles: int = 1,
    status_publisher: FakeStatusPublisher | None = None,
) -> tuple[int, RecordingStream, RecordingStream, RecordingDelay]:
    monkeypatch.setattr(
        app_main,
        "_compose_homeassistant",
        lambda *arguments: _composition(workflow, status_publisher),
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
    publisher = FakeStatusPublisher()

    status, stdout, stderr, delay = _run_with_workflow(
        monkeypatch,
        workflow,
        max_cycles=2,
        status_publisher=publisher,
    )

    assert status == 0
    assert workflow.calls == 2
    assert delay.durations == [timedelta(seconds=300)]
    assert stdout.text.count("sync complete:") == 2
    assert "products=1" in stdout.text
    assert "status_published=true" in stdout.text
    assert publisher.calls == [
        ((create_product(),), TIMESTAMP, 0, 0),
        ((), TIMESTAMP, 0, 0),
    ]
    assert stdout.text.endswith(
        "watch complete: cycles=2 provider_error_cycles=0 "
        "status_error_cycles=0\n"
    )
    assert stderr.text == ""


def test_provider_error_cycles_continue_and_return_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = FakeWorkflow((_result(provider_error=True), _result()))
    publisher = FakeStatusPublisher()

    status, stdout, stderr, delay = _run_with_workflow(
        monkeypatch,
        workflow,
        max_cycles=2,
        status_publisher=publisher,
    )

    assert status == 1
    assert workflow.calls == 2
    assert len(delay.durations) == 1
    assert "provider error: Lidl failed" in stderr.text
    assert "provider_error_cycles=1" in stdout.text
    assert publisher.calls[0][3] == 1


def test_status_errors_continue_and_return_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = FakeStatusPublisher(HomeAssistantError("state failed"))
    workflow = FakeWorkflow((_result(product=True), _result()))

    status, stdout, stderr, delay = _run_with_workflow(
        monkeypatch,
        workflow,
        max_cycles=2,
        status_publisher=publisher,
    )

    assert status == 1
    assert workflow.calls == 2
    assert len(delay.durations) == 1
    assert len(publisher.calls) == 2
    assert stderr.text.count("status error: state failed") == 2
    assert stdout.text.count("status_published=false") == 2
    assert stdout.text.endswith(
        "watch complete: cycles=2 provider_error_cycles=0 "
        "status_error_cycles=2\n"
    )


def test_unexpected_status_failure_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("publisher bug")
    publisher = FakeStatusPublisher(failure)

    with pytest.raises(RuntimeError) as captured:
        _run_with_workflow(
            monkeypatch,
            FakeWorkflow((_result(),)),
            status_publisher=publisher,
        )

    assert captured.value is failure


@pytest.mark.parametrize(
    "failure",
    [
        StateStoreError("state failed"),
        RuleError("rule failed"),
        NotificationError("delivery failed"),
        NotificationReservationError("reservation failed"),
        DailyDigestReservationError("digest reservation failed"),
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
    assert stdout.text.endswith(
        "watch stopped: cycles=1 provider_error_cycles=0 "
        "status_error_cycles=0\n"
    )
    assert stderr.text == ""


def test_run_maps_supervisor_termination_to_success_after_completed_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delay = RecordingDelay(failure=_TerminationRequested())

    status, stdout, stderr, _ = _run_with_workflow(
        monkeypatch,
        FakeWorkflow((_result(),)),
        delay=delay,
        max_cycles=2,
    )

    assert status == 0
    assert stdout.text.endswith(
        "watch stopped: cycles=1 provider_error_cycles=0 "
        "status_error_cycles=0\n"
    )
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


def test_command_stream_without_retention_still_runs_monitoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = FakeWorkflow((_result(),))
    monkeypatch.setattr(
        app_main,
        "_compose_homeassistant",
        lambda *arguments: _composition(workflow),
    )

    status = run(
        create_options(),
        "token",
        RecordingStream(),
        RecordingStream(),
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        max_cycles=1,
        command_input=StringIO(""),
    )

    assert status == 0
    assert workflow.calls == 1


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
        ("command_input", object(), TypeError, "command_input"),
        ("migration_directory", "share", TypeError, "migration_directory"),
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
        "command_input": None,
        "migration_directory": Path("share"),
    }
    values[field] = value

    with pytest.raises(exception_type, match=message):
        run(**values)


def test_requested_migration_import_completes_before_composition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    options = create_options()
    source = tmp_path / "source"
    source.mkdir()
    (source / "state.json").write_text(
        '{"schema_version":1,"snapshots":{}}\n',
        encoding="utf-8",
    )
    share = tmp_path / "share"
    export = ZipMigrationArchive(share).export(
        source,
        options,
        TIMESTAMP,
        "0.27.0",
    )
    target = tmp_path / "target"
    imported_options = {
        **options,
        "migration_import_file": export.archive_file.name,
        "migration_import_sha256": export.archive_sha256,
        "migration_import_confirmation": "IMPORT_MIGRATION",
    }

    def compose(*arguments: object) -> _HomeAssistantComposition:
        assert (target / "state.json").is_file()
        return _composition(FakeWorkflow((_result(),)))

    monkeypatch.setattr(app_main, "_compose_homeassistant", compose)
    stdout = RecordingStream()
    status = run(
        imported_options,
        "token",
        stdout,
        RecordingStream(),
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        data_directory=target,
        migration_directory=share,
        max_cycles=1,
    )

    assert status == 0
    assert "migration import complete" in stdout.text


def test_requested_migration_failure_prevents_composition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    composed = False

    def compose(*arguments: object) -> _HomeAssistantComposition:
        nonlocal composed
        composed = True
        return _composition(FakeWorkflow((_result(),)))

    monkeypatch.setattr(app_main, "_compose_homeassistant", compose)
    stderr = RecordingStream()
    status = run(
        create_options(
            migration_import_file="missing.zip",
            migration_import_sha256="a" * 64,
            migration_import_confirmation="IMPORT_MIGRATION",
        ),
        "token",
        RecordingStream(),
        stderr,
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        data_directory=tmp_path / "data",
        migration_directory=tmp_path / "share",
        max_cycles=1,
    )

    assert status == 1
    assert "migration directory must be a regular directory" in stderr.text
    assert composed is False
