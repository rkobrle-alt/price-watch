"""Immutable result of a bounded interval schedule."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    """Report the number of successfully completed scheduled cycles."""

    cycles_completed: int

    def __post_init__(self) -> None:
        """Validate the completed-cycle count."""
        if isinstance(self.cycles_completed, bool) or not isinstance(
            self.cycles_completed,
            int,
        ):
            raise TypeError("cycles_completed must be an int")
        if self.cycles_completed < 0:
            raise ValueError("cycles_completed cannot be negative")
