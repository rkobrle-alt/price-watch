"""Tests for private Home Assistant process lifecycle handling."""

import signal
from collections.abc import Callable
from types import FrameType
from typing import cast

import pytest

from applications.homeassistant.lifecycle import (
    _TerminationRequested,
    _raise_termination_request,
    _termination_signal_handler,
)


def test_termination_handler_raises_private_control_signal() -> None:
    """SIGTERM is converted without being confused with Ctrl+C."""
    with pytest.raises(_TerminationRequested):
        _raise_termination_request(signal.SIGTERM, None)


@pytest.mark.parametrize("failure", [None, RuntimeError("body failed")])
def test_termination_handler_restores_preceding_handler(
    monkeypatch: pytest.MonkeyPatch,
    failure: RuntimeError | None,
) -> None:
    """The caller's process handler is restored on every context exit."""
    previous = cast(Callable[[int, FrameType | None], None], object())
    calls: list[tuple[signal.Signals, object]] = []

    def replace_handler(signal_number: signal.Signals, handler: object) -> object:
        calls.append((signal_number, handler))
        return previous

    monkeypatch.setattr(signal, "signal", replace_handler)

    if failure is None:
        with _termination_signal_handler():
            pass
    else:
        with pytest.raises(RuntimeError) as captured:
            with _termination_signal_handler():
                raise failure
        assert captured.value is failure

    assert calls == [
        (signal.SIGTERM, _raise_termination_request),
        (signal.SIGTERM, previous),
    ]
