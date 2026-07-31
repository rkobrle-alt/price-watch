"""Tests for the standard-library text HTTP client."""

from gzip import compress
from email.message import Message
from urllib.error import URLError

import pytest

from infrastructure.http import HttpClientError, TextHttpClient, UrllibTextHttpClient


class _Response:
    def __init__(
        self,
        body: bytes,
        charset: str | None,
        content_encoding: str | None = None,
    ) -> None:
        self._body = body
        self.headers = Message()
        if charset is not None:
            self.headers["Content-Type"] = f"text/html; charset={charset}"
        if content_encoding is not None:
            self.headers["Content-Encoding"] = content_encoding

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _as_contract(client: TextHttpClient) -> TextHttpClient:
    return client


def test_urllib_client_implements_text_http_contract() -> None:
    client = UrllibTextHttpClient()

    assert _as_contract(client) is client


@pytest.mark.parametrize("timeout", [True, 1.5, "10"])
def test_constructor_rejects_invalid_timeout_type(timeout: object) -> None:
    with pytest.raises(TypeError, match="timeout_seconds"):
        UrllibTextHttpClient(timeout_seconds=timeout)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout", [0, -1])
def test_constructor_rejects_non_positive_timeout(timeout: int) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        UrllibTextHttpClient(timeout_seconds=timeout)


def test_constructor_rejects_invalid_user_agent_type() -> None:
    with pytest.raises(TypeError, match="user_agent"):
        UrllibTextHttpClient(user_agent=1)  # type: ignore[arg-type]


def test_constructor_rejects_blank_user_agent() -> None:
    with pytest.raises(ValueError, match="blank"):
        UrllibTextHttpClient(user_agent=" \t")


@pytest.mark.parametrize("url", [None, 42])
def test_get_rejects_invalid_url_type(url: object) -> None:
    with pytest.raises(TypeError, match="url"):
        UrllibTextHttpClient().get(url)  # type: ignore[arg-type]


def test_get_rejects_blank_url() -> None:
    with pytest.raises(ValueError, match="blank"):
        UrllibTextHttpClient().get("  ")


@pytest.mark.parametrize(
    ("body", "charset", "expected"),
    [
        ("PARKSIDE".encode(), None, "PARKSIDE"),
        ("nářadí".encode("windows-1250"), "windows-1250", "nářadí"),
    ],
)
def test_get_uses_configuration_and_response_charset(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    charset: str | None,
    expected: str,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response(body, charset)

    monkeypatch.setattr(
        "infrastructure.http.urllib_client.urlopen",
        fake_urlopen,
    )
    client = UrllibTextHttpClient(timeout_seconds=7, user_agent="PriceWatch/Test")

    assert client.get("https://www.lidl.cz/product") == expected
    request = captured["request"]
    assert request.get_header("User-agent") == "PriceWatch/Test"  # type: ignore[attr-defined]
    assert captured["timeout"] == 7


def test_get_decompresses_gzip_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = compress("nářadí".encode())
    monkeypatch.setattr(
        "infrastructure.http.urllib_client.urlopen",
        lambda request, timeout: _Response(body, None, "GZip"),
    )

    assert UrllibTextHttpClient().get("https://www.lidl.cz/product") == "nářadí"


def test_get_wraps_operational_failure_and_preserves_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = URLError("offline")

    def failing_urlopen(request: object, timeout: int) -> _Response:
        raise failure

    monkeypatch.setattr(
        "infrastructure.http.urllib_client.urlopen",
        failing_urlopen,
    )

    with pytest.raises(HttpClientError, match="failed to retrieve") as captured:
        UrllibTextHttpClient().get("https://www.lidl.cz/product")

    assert captured.value.__cause__ is failure


def test_get_wraps_decoding_failure_and_preserves_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "infrastructure.http.urllib_client.urlopen",
        lambda request, timeout: _Response(b"\xff", "utf-8"),
    )

    with pytest.raises(HttpClientError) as captured:
        UrllibTextHttpClient().get("https://www.lidl.cz/product")

    assert isinstance(captured.value.__cause__, UnicodeDecodeError)
