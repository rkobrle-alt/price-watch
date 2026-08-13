"""Immutable provider-neutral promotion values."""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class DailyPromotion:
    """Describe one current provider promotion for a daily digest."""

    text: str
    url: str | None = None

    def __post_init__(self) -> None:
        """Validate actionable, channel-neutral promotion content."""
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not self.text.strip():
            raise ValueError("text cannot be blank")
        if self.url is not None:
            if not isinstance(self.url, str):
                raise TypeError("url must be a string or None")
            parsed = urlparse(self.url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("url must be an absolute HTTPS URL")
