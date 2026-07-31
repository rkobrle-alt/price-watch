"""Tests for Core scheduling contracts."""

import inspect
from datetime import timedelta

import core.scheduler as scheduler_api
from core.scheduler import Delay, SchedulerError


class FakeDelay:
    """Structurally implement the delay contract."""

    def wait(self, duration: timedelta) -> None:
        """Accept a duration without blocking."""


def test_core_scheduler_api_is_explicit_and_documented() -> None:
    assert scheduler_api.__all__ == ["Delay", "SchedulerError"]
    assert scheduler_api.Delay is Delay
    assert scheduler_api.SchedulerError is SchedulerError
    assert inspect.getdoc(Delay)
    assert inspect.getdoc(Delay.wait)
    assert inspect.getdoc(SchedulerError)


def test_delay_protocol_supports_structural_conformance() -> None:
    assert isinstance(FakeDelay(), Delay)
