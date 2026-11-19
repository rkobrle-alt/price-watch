"""Infrastructure HTTP exceptions."""


class HttpClientError(Exception):
    """Report an operational HTTP retrieval or decoding failure."""


class HttpResourceNotFoundError(HttpClientError):
    """Report an HTTP resource explicitly missing (404 or 410)."""
