"""Public API for product state abstractions."""

from core.state.exceptions import StateStoreError
from core.state.history import ObservationHistory
from core.state.latest import LatestSnapshotReader
from core.state.retention import (
    ObservationRetentionManager,
    ObservationRetentionPlan,
    ObservationRetentionResult,
)
from core.state.snapshot import StateSnapshot
from core.state.statistics import ObservationStatistics, ObservationStatisticsReader
from core.state.store import StateStore

__all__ = [
    "LatestSnapshotReader",
    "ObservationHistory",
    "ObservationRetentionManager",
    "ObservationRetentionPlan",
    "ObservationRetentionResult",
    "ObservationStatistics",
    "ObservationStatisticsReader",
    "StateSnapshot",
    "StateStore",
    "StateStoreError",
]
