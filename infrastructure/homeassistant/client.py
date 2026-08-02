"""Structural Home Assistant client contracts."""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class HomeAssistantClient(Protocol):
    """Invoke services exposed by Home Assistant Core."""

    def call_service(
        self,
        domain: str,
        service: str,
        data: Mapping[str, object],
    ) -> None:
        """Call one Home Assistant service with explicit data."""
        ...


@runtime_checkable
class HomeAssistantStateClient(Protocol):
    """Create or update read-only Home Assistant state representations."""

    def set_state(
        self,
        entity_id: str,
        state: str,
        attributes: Mapping[str, object],
    ) -> None:
        """Publish one explicit entity state and its attributes."""
        ...
