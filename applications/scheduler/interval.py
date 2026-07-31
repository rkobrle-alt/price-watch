"""Serial fixed-delay application scheduling."""

from collections.abc import Callable
from datetime import timedelta
from typing import cast

from applications.scheduler.result import ScheduleResult
from core.scheduler import Delay


class IntervalScheduler:
    """Run one injected cycle repeatedly without overlapping executions."""

    def __init__(
        self,
        cycle: Callable[[], None],
        delay: Delay,
    ) -> None:
        """Configure a scheduler without invoking the cycle or delay."""
        if not callable(cycle):
            raise TypeError("cycle must be callable")
        if not callable(getattr(delay, "wait", None)):
            raise TypeError("delay must expose a callable wait method")
        self._cycle = cycle
        self._delay = cast(Delay, delay)

    def run(
        self,
        interval: timedelta,
        max_cycles: int | None = None,
    ) -> ScheduleResult:
        """Run immediately and then after each fixed delay until bounded."""
        _validate_interval(interval)
        _validate_max_cycles(max_cycles)
        completed = 0

        while max_cycles is None or completed < max_cycles:
            self._cycle()
            completed += 1
            if max_cycles is None or completed < max_cycles:
                self._delay.wait(interval)

        return ScheduleResult(cycles_completed=completed)


def _validate_interval(interval: object) -> None:
    if not isinstance(interval, timedelta):
        raise TypeError("interval must be a timedelta")
    if interval <= timedelta(0):
        raise ValueError("interval must be positive")


def _validate_max_cycles(max_cycles: object) -> None:
    if max_cycles is None:
        return
    if isinstance(max_cycles, bool) or not isinstance(max_cycles, int):
        raise TypeError("max_cycles must be an int or None")
    if max_cycles <= 0:
        raise ValueError("max_cycles must be positive")
