"""Tests for the Home Assistant Supervisor process adapter."""

import importlib
from pathlib import Path
from typing import cast

import pytest

from applications.homeassistant.lifecycle import _TerminationRequested
from core.configuration import ConfigurationError
from tests.unit.homeassistant_app.helpers import RecordingStream, create_options

app_main = importlib.import_module("applications.homeassistant.main")


@pytest.mark.parametrize("token", [None, " "])
def test_main_requires_supervisor_token(
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
) -> None:
    stderr = RecordingStream()
    monkeypatch.setattr(app_main.sys, "stderr", stderr)
    if token is None:
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    else:
        monkeypatch.setenv("SUPERVISOR_TOKEN", token)

    assert app_main.main() == 2
    assert stderr.text == "error: SUPERVISOR_TOKEN is required\n"


def test_main_maps_json_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = RecordingStream()
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr(app_main.sys, "stderr", stderr)
    monkeypatch.setattr(
        app_main.JsonConfigurationLoader,
        "load",
        lambda self, path: (_ for _ in ()).throw(ConfigurationError("bad JSON")),
    )

    assert app_main.main() == 2
    assert stderr.text == "error: bad JSON\n"


def test_main_supplies_real_process_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    options = create_options()
    monkeypatch.setenv("SUPERVISOR_TOKEN", "injected-token")
    monkeypatch.setattr(
        app_main.JsonConfigurationLoader,
        "load",
        lambda self, path: options,
    )

    def fake_run(*arguments: object, **keywords: object) -> int:
        captured["arguments"] = arguments
        captured["keywords"] = keywords
        return 7

    monkeypatch.setattr(app_main, "run", fake_run)

    assert app_main.main() == 7
    arguments = cast(tuple[object, ...], captured["arguments"])
    assert arguments[0] is options
    assert arguments[1] == "injected-token"
    assert callable(arguments[4])
    assert callable(arguments[5])
    assert callable(getattr(arguments[6], "wait", None))
    assert cast(dict[str, object], captured["keywords"])["data_directory"] == Path(
        "/data"
    )


def test_main_maps_termination_before_monitoring_to_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = RecordingStream()
    monkeypatch.setenv("SUPERVISOR_TOKEN", "injected-token")
    monkeypatch.setattr(app_main.sys, "stdout", stdout)
    monkeypatch.setattr(
        app_main.JsonConfigurationLoader,
        "load",
        lambda self, path: create_options(),
    )
    monkeypatch.setattr(
        app_main,
        "run",
        lambda *arguments, **keywords: (_ for _ in ()).throw(
            _TerminationRequested()
        ),
    )

    assert app_main.main() == 0
    assert stdout.text == "shutdown complete: before monitoring\n"


def test_main_propagates_unexpected_loader_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("bug")
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr(
        app_main.JsonConfigurationLoader,
        "load",
        lambda self, path: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(RuntimeError) as captured:
        app_main.main()

    assert captured.value is failure
