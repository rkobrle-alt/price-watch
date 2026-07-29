"""Provider metadata value."""

from dataclasses import dataclass

from core.domain import ProviderId


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """Immutable identifying and descriptive information for a provider."""

    id: ProviderId
    display_name: str
    version: str
    country: str
    homepage: str
