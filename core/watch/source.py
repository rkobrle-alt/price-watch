"""Provider-neutral boundary for resolving user choices against observations."""

from typing import Protocol

from core.state import StateSnapshot
from core.watch.model import DigestWatchPreferences


class DigestWatchPreferenceSource(Protocol):
    """Resolve durable user options to stable current product identities."""

    def resolve(self, snapshots: tuple[StateSnapshot, ...]) -> DigestWatchPreferences:
        """Return validated choices for the supplied observed products."""
        ...
