"""Tests for real process and module entry-point adapters."""

import importlib
import runpy
import sys
from datetime import datetime
from typing import Callable
from uuid import UUID

import pytest

import applications.cli as cli_package
from infrastructure.scheduler import SystemDelay
from tests.unit.cli.helpers import RecordingStream


def test_main_supplies_real_process_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_module = importlib.import_module("applications.cli.main")
    stdout = RecordingStream()
    stderr = RecordingStream()
    captured: dict[str, object] = {}

    def fake_run(
        argv: tuple[str, ...],
        output: object,
        error_output: object,
        clock: Callable[[], datetime],
        notification_id_factory: Callable[[], UUID],
        *,
        delay: object,
    ) -> int:
        captured.update(
            argv=argv,
            stdout=output,
            stderr=error_output,
            timestamp=clock(),
            notification_id=notification_id_factory(),
            delay=delay,
        )
        return 7

    monkeypatch.setattr(main_module, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["price-watch", "version"])
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    assert main_module.main() == 7
    assert captured["argv"] == ("version",)
    assert captured["stdout"] is stdout
    assert captured["stderr"] is stderr
    timestamp = captured["timestamp"]
    assert isinstance(timestamp, datetime)
    assert timestamp.tzinfo is not None
    assert isinstance(captured["notification_id"], UUID)
    assert isinstance(captured["delay"], SystemDelay)


def test_python_module_entrypoint_exits_with_main_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_package, "main", lambda: 9)

    with pytest.raises(SystemExit) as captured:
        runpy.run_module("applications.cli", run_name="__main__")

    assert captured.value.code == 9
