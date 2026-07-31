"""Application configuration loading boundary."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ConfigurationLoader(Protocol):
    """Load a neutral configuration document from an explicit path."""

    def load(self, path: Path) -> Mapping[str, object]:
        """Return the decoded document without application validation."""
        ...
