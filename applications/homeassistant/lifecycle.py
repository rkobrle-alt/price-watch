"""Private operating-system lifecycle handling for the Home Assistant App."""

import signal
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType


class _TerminationRequested(BaseException):
    """Signal a Supervisor-requested graceful process termination."""


def _raise_termination_request(
    signal_number: int,
    frame: FrameType | None,
) -> None:
    """Convert an operating-system termination signal into process control."""
    _ = signal_number, frame
    raise _TerminationRequested


@contextmanager
def _termination_signal_handler() -> Iterator[None]:
    """Install the App termination handler and restore its predecessor."""
    previous = signal.signal(signal.SIGTERM, _raise_termination_request)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
