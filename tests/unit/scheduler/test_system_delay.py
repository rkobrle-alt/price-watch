"""Tests for the Infrastructure system delay."""

from datetime import timedelta
from typing import cast

import pytest

from core.scheduler import Delay, SchedulerError
from infrastructure.scheduler import SystemDelay


def test_system_delay_implements_protocol_and_converts_duration() -> None:
    seconds: list[float] = []
    delay = SystemDelay(seconds.append)

    delay.wait(timedelta(seconds=2, microseconds=500_000))

    assert isinstance(delay, Delay)
    assert seconds == [2.5]


def test_system_delay_supports_default_sleep_dependency() -> None:
    delay = SystemDelay()

    assert callable(delay._sleep)


@pytest.mark.parametrize("sleep", [None, 1])
def test_system_delay_rejects_invalid_sleep(sleep: object) -> None:
    with pytest.raises(TypeError):
        SystemDelay(cast(object, sleep))


@pytest.mark.parametrize(
    ("duration", "exception_type"),
    [
        (cast(timedelta, 1), TypeError),
        (timedelta(0), ValueError),
        (timedelta(seconds=-1), ValueError),
    ],
)
def test_system_delay_rejects_invalid_duration(
    duration: timedelta,
    exception_type: type[Exception],
) -> None:
    with pytest.raises(exception_type):
        SystemDelay(lambda _: None).wait(duration)


@pytest.mark.parametrize(
    "failure",
    [OSError("unavailable"), OverflowError("too large")],
)
def test_system_delay_translates_operational_failure(failure: Exception) -> None:
    def fail(_: float) -> None:
        raise failure

    with pytest.raises(SchedulerError) as captured:
        SystemDelay(fail).wait(timedelta(seconds=1))

    assert str(captured.value) == f"system delay failed: {failure}"
    assert captured.value.__cause__ is failure


@pytest.mark.parametrize("failure", [RuntimeError("bug"), KeyboardInterrupt()])
def test_system_delay_propagates_unexpected_failure(
    failure: BaseException,
) -> None:
    def fail(_: float) -> None:
        raise failure

    with pytest.raises(type(failure)) as captured:
        SystemDelay(fail).wait(timedelta(seconds=1))

    assert captured.value is failure
