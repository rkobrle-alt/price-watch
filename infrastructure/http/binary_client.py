"""Binary HTTP client contract."""

from typing import Protocol


class BinaryHttpClient(Protocol):
    """Retrieve undecoded bytes from an HTTP resource."""

    def get(self, url: str) -> bytes:
        """Return the response bytes from *url*."""
        ...
