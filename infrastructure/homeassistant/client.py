"""Structural Home Assistant service client contract."""

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
