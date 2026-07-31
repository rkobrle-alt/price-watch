"""Delay boundary used by application schedulers."""

from datetime import timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Delay(Protocol):
    """Wait for an explicit duration at an Infrastructure boundary."""

    def wait(self, duration: timedelta) -> None:
        """Block for the supplied positive duration."""
        ...
