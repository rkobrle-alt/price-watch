"""Provider SDK exceptions."""


class ProviderError(Exception):
    """Base exception for provider and provider-registry failures."""


class ProviderTransportError(ProviderError):
    """Report a failure retrieving provider data."""


class ProviderProductNotFoundError(ProviderTransportError):
    """Report an explicitly missing product resource without inventing stock."""

    def __init__(self, message: str, url: str) -> None:
        """Retain the exact requested URL for downstream reconciliation."""
        if not isinstance(url, str):
            raise TypeError("url must be a string")
        if not url.strip():
            raise ValueError("url cannot be blank")
        super().__init__(message)
        self.url = url


class ProviderDataError(ProviderError):
    """Report provider data that cannot be translated safely."""
