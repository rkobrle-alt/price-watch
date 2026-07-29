"""Registry for installed provider implementations."""

from core.domain import ProviderId
from core.provider.contract import Provider
from core.provider.error import ProviderError


class ProviderRegistry:
    """Maintain provider implementations indexed by their domain identifiers."""

    def __init__(self) -> None:
        """Create an empty provider registry."""
        self._providers: dict[ProviderId, Provider] = {}

    def register(self, provider: Provider) -> None:
        """Register a provider, rejecting an already registered identifier."""
        if provider.id in self._providers:
            raise ProviderError(f"provider {provider.id.value} is already registered")
        self._providers[provider.id] = provider

    def unregister(self, provider_id: ProviderId) -> Provider:
        """Remove and return a provider by identifier."""
        try:
            return self._providers.pop(provider_id)
        except KeyError as error:
            raise ProviderError(f"provider {provider_id.value} is not registered") from error

    def get(self, provider_id: ProviderId) -> Provider:
        """Return a registered provider by identifier."""
        try:
            return self._providers[provider_id]
        except KeyError as error:
            raise ProviderError(f"provider {provider_id.value} is not registered") from error

    def list(self) -> tuple[Provider, ...]:
        """Return registered providers in registration order."""
        return tuple(self._providers.values())
