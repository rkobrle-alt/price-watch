"""Read-only application boundary for historical price assessments."""

from datetime import datetime
from typing import Protocol

from core.pricing.model import PriceHistoryAssessment
from core.state import StateSnapshot


class PriceHistoryAssessmentSource(Protocol):
    """Supply deterministic assessments backed by retained observations."""

    def assess(
        self, snapshots: tuple[StateSnapshot, ...], timestamp: datetime,
    ) -> tuple[PriceHistoryAssessment, ...]:
        """Assess only the requested current product observations."""
        ...
