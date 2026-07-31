"""Text HTTP client contract."""

from typing import Protocol


class TextHttpClient(Protocol):
    """Retrieve text content from an HTTP resource."""

    def get(self, url: str) -> str:
        """Return decoded text content from *url*."""
        ...
