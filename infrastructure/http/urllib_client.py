"""Standard-library implementation of text HTTP retrieval."""

from gzip import decompress
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from infrastructure.http.exceptions import HttpClientError


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
        """Retrieve *url* and decode its response body as text."""
        if not isinstance(url, str):
            raise TypeError("url must be a str")
        if not url.strip():
            raise ValueError("url cannot be blank")

        request = Request(url, headers={"User-Agent": self._user_agent})
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                payload = response.read()
                content_encoding = response.headers.get("Content-Encoding", "")
                if content_encoding.casefold() == "gzip":
                    payload = decompress(payload)
                return payload.decode(charset)
        except (HTTPError, URLError, OSError, UnicodeError) as error:
            raise HttpClientError(f"failed to retrieve {url}") from error
