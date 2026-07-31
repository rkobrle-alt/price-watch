"""Tests for deterministic fixed-delay scheduling."""

from dataclasses import FrozenInstanceError
from datetime import timedelta
from typing import cast

import pytest

from applications.scheduler import IntervalScheduler, ScheduleResult


class RecordingDelay:
    """Record requested waits and optionally raise."""

    def __init__(self, failure: BaseException | None = None) -> None:
        """Configure an optional wait failure."""
        self.durations: list[timedelta] = []
        self.failure = failure

    def wait(self, duration: timedelta) -> None:
        """Record one wait and raise the configured failure."""
        self.durations.append(duration)
        if self.failure is not None:
            raise self.failure


def test_bounded_schedule_runs_immediately_and_waits_only_between_cycles() -> None:
    events: list[str] = []
    delay = RecordingDelay()

    def cycle() -> None:
        events.append("cycle")

    result = IntervalScheduler(cycle, delay).run(timedelta(seconds=15), 3)

    assert result == ScheduleResult(cycles_completed=3)
    assert events == ["cycle", "cycle", "cycle"]
    assert delay.durations == [timedelta(seconds=15), timedelta(seconds=15)]


def test_single_bounded_cycle_does_not_wait() -> None:
    delay = RecordingDelay()

    result = IntervalScheduler(lambda: None, delay).run(timedelta(seconds=1), 1)

    assert result.cycles_completed == 1
    assert delay.durations == []


def test_unbounded_schedule_continues_until_cycle_raises() -> None:
    failure = RuntimeError("stop")
    calls = 0
    delay = RecordingDelay()

    def cycle() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise failure

    with pytest.raises(RuntimeError) as captured:
        IntervalScheduler(cycle, delay).run(timedelta(seconds=2))

    assert captured.value is failure
    assert calls == 3
    assert delay.durations == [timedelta(seconds=2), timedelta(seconds=2)]


def test_delay_failure_propagates_without_starting_another_cycle() -> None:
    failure = OSError("wait failed")
    delay = RecordingDelay(failure)
    calls = 0

    def cycle() -> None:
        nonlocal calls
        calls += 1

    with pytest.raises(OSError) as captured:
        IntervalScheduler(cycle, delay).run(timedelta(seconds=2), 2)

    assert captured.value is failure
    assert calls == 1


@pytest.mark.parametrize("cycle", [None, 1])
def test_scheduler_rejects_non_callable_cycle(cycle: object) -> None:
    with pytest.raises(TypeError):
        IntervalScheduler(cast(object, cycle), RecordingDelay())


@pytest.mark.parametrize("delay", [None, object()])
def test_scheduler_rejects_invalid_delay(delay: object) -> None:
    with pytest.raises(TypeError):
        IntervalScheduler(lambda: None, cast(object, delay))


@pytest.mark.parametrize(
    ("interval", "exception_type"),
    [
        (cast(timedelta, 1), TypeError),
        (timedelta(0), ValueError),
        (timedelta(seconds=-1), ValueError),
    ],
)
def test_scheduler_rejects_invalid_interval(
    interval: timedelta,
    exception_type: type[Exception],
) -> None:
    with pytest.raises(exception_type):
        IntervalScheduler(lambda: None, RecordingDelay()).run(interval, 1)


@pytest.mark.parametrize(
    ("max_cycles", "exception_type"),
    [
        (True, TypeError),
        (cast(int, "2"), TypeError),
        (0, ValueError),
        (-1, ValueError),
    ],
)
def test_scheduler_rejects_invalid_cycle_limit(
    max_cycles: int,
    exception_type: type[Exception],
) -> None:
    with pytest.raises(exception_type):
        IntervalScheduler(lambda: None, RecordingDelay()).run(
            timedelta(seconds=1),
            max_cycles,
        )


@pytest.mark.parametrize(
    ("cycles_completed", "exception_type"),
    [
        (True, TypeError),
        (cast(int, "1"), TypeError),
        (-1, ValueError),
    ],
)
def test_schedule_result_rejects_invalid_count(
    cycles_completed: int,
    exception_type: type[Exception],
) -> None:
    with pytest.raises(exception_type):
        ScheduleResult(cycles_completed)


def test_schedule_result_is_immutable() -> None:
    result = ScheduleResult(1)

    with pytest.raises(FrozenInstanceError):
        result.cycles_completed = 2
