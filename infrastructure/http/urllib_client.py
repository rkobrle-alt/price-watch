"""Standard-library implementation of text HTTP retrieval."""

from gzip import decompress
from http.client import BadStatusLine, IncompleteRead
from socket import gaierror
from ssl import SSLError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from infrastructure.http.exceptions import HttpClientError

_MAX_READ_ATTEMPTS = 2


class UrllibTextHttpClient:
    """Retrieve and decode text resources with :mod:`urllib`."""

    def __init__(
        self,
        timeout_seconds: int = 10,
        user_agent: str = "PriceWatch/0.6",
    ) -> None:
        """Configure request timeout and the explicit user-agent header."""
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            raise TypeError("timeout_seconds must be an int")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if not isinstance(user_agent, str):
            raise TypeError("user_agent must be a str")
        if not user_agent.strip():
            raise ValueError("user_agent cannot be blank")
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    def get(self, url: str) -> str:
        """Retrieve *url*, retrying one incomplete read, and decode its body."""
        if not isinstance(url, str):
            raise TypeError("url must be a str")
        if not url.strip():
            raise ValueError("url cannot be blank")

        request = Request(url, headers={"User-Agent": self._user_agent})
        attempt = 0
        while True:
            attempt += 1
            try:
                with urlopen(request, timeout=self._timeout_seconds) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    payload = response.read()
                    content_encoding = response.headers.get("Content-Encoding", "")
                    if content_encoding.casefold() == "gzip":
                        payload = decompress(payload)
                    return payload.decode(charset)
            except IncompleteRead as error:
                if attempt == _MAX_READ_ATTEMPTS:
                    raise HttpClientError(
                        f"failed to retrieve {url} "
                        f"[incomplete response after {attempt} attempts]"
                    ) from error
            except BadStatusLine as error:
                raise HttpClientError(
                    f"failed to retrieve {url} [HTTP protocol error]"
                ) from error
            except (HTTPError, URLError, OSError, UnicodeError) as error:
                raise HttpClientError(
                    f"failed to retrieve {url} [{_failure_detail(error)}]"
                ) from error


def _failure_detail(error: BaseException) -> str:
    """Describe known failure categories without exposing response data."""
    if isinstance(error, HTTPError):
        return f"HTTP {error.code}"
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, TimeoutError):
        return "timeout"
    if isinstance(reason, gaierror):
        return "DNS error"
    if isinstance(reason, SSLError):
        return "TLS error"
    if isinstance(reason, ConnectionError):
        return "connection error"
    if isinstance(error, URLError):
        return "network error"
    if isinstance(error, UnicodeError):
        return "decoding error"
    return "I/O error"
