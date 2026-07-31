"""System-backed implementation of the Core delay boundary."""

import time
from collections.abc import Callable
from datetime import timedelta

from core.scheduler import SchedulerError


class SystemDelay:
    """Wait using an injected standard-library-compatible sleep callable."""

    def __init__(
        self,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure the concrete blocking operation."""
        if not callable(sleep):
            raise TypeError("sleep must be callable")
        self._sleep = sleep

    def wait(self, duration: timedelta) -> None:
        """Block for a positive duration and translate operational failures."""
        if not isinstance(duration, timedelta):
            raise TypeError("duration must be a timedelta")
        if duration <= timedelta(0):
            raise ValueError("duration must be positive")
        try:
            self._sleep(duration.total_seconds())
        except (OSError, OverflowError) as error:
            raise SchedulerError(f"system delay failed: {error}") from error
