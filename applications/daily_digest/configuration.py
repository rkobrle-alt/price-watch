"""Immutable daily digest application configuration."""

from dataclasses import dataclass
from datetime import time

from core.domain import Percentage


@dataclass(frozen=True, slots=True)
class DailyDigestConfig:
    """Configure local delivery time and qualifying discount threshold."""

    delivery_time: time
    minimum_discount: Percentage

    def __post_init__(self) -> None:
        """Validate local minute precision and exact threshold type."""
        if not isinstance(self.delivery_time, time):
            raise TypeError("delivery_time must be a time")
        if self.delivery_time.tzinfo is not None:
            raise ValueError("delivery_time must be a naive local time")
        if self.delivery_time.second or self.delivery_time.microsecond:
            raise ValueError("delivery_time must have minute precision")
        if not isinstance(self.minimum_discount, Percentage):
            raise TypeError("minimum_discount must be a Percentage")
