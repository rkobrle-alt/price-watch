"""Bounded standard-library implementation of binary HTTP retrieval."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from infrastructure.http.exceptions import HttpClientError

_DEFAULT_MAX_RESPONSE_BYTES = 20 * 1024 * 1024


class UrllibBinaryHttpClient:
    """Retrieve bounded binary resources with urllib."""

    def __init__(
        self,
        timeout_seconds: int = 10,
        user_agent: str = "PriceWatch/0.15",
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
        opener: Callable[..., AbstractContextManager[BinaryIO]] = urlopen,
    ) -> None:
        """Configure timeout, request identity, size limit and URL opener."""
        self._timeout_seconds = _positive_int(timeout_seconds, "timeout_seconds")
        if not isinstance(user_agent, str):
            raise TypeError("user_agent must be a str")
        if not user_agent.strip():
            raise ValueError("user_agent cannot be blank")
        self._max_response_bytes = _positive_int(
            max_response_bytes, "max_response_bytes"
        )
        if not callable(opener):
            raise TypeError("opener must be callable")
        self._user_agent = user_agent
        self._opener = opener

    def get(self, url: str) -> bytes:
        """Retrieve *url* as bytes within the configured response-size limit."""
        _validate_http_url(url)
        request = Request(url, headers={"User-Agent": self._user_agent})
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = response.read(self._max_response_bytes + 1)
            if not isinstance(payload, bytes):
                raise TypeError("binary response must contain bytes")
            if len(payload) > self._max_response_bytes:
                raise ValueError("response exceeds max_response_bytes")
            return payload
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            raise HttpClientError(f"failed to retrieve {url}") from error


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _validate_http_url(url: object) -> None:
    if not isinstance(url, str):
        raise TypeError("url must be a str")
    if not url.strip():
        raise ValueError("url cannot be blank")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("url must be an HTTP or HTTPS URL")
