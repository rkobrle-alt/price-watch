"""Read-only access to the latest snapshot of every observed product."""

from typing import Protocol

from core.state.snapshot import StateSnapshot


class LatestSnapshotReader(Protocol):
    """Return one latest immutable snapshot per observed product."""

    def latest_snapshots(self) -> tuple[StateSnapshot, ...]:
        """Return latest snapshots in deterministic product-identifier order."""
        ...
