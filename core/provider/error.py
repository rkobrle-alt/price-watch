"""Provider SDK exceptions."""


class ProviderError(Exception):
    """Base exception for provider and provider-registry failures."""


class ProviderTransportError(ProviderError):
    """Report a failure retrieving provider data."""


class ProviderDataError(ProviderError):
    """Report provider data that cannot be translated safely."""
