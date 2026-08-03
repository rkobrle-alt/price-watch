"""Tests for bounded standard-library binary HTTP retrieval."""

from typing import cast
from urllib.error import URLError

import pytest

from infrastructure.http import (
    BinaryHttpClient,
    HttpClientError,
    UrllibBinaryHttpClient,
)


class _Response:
    def __init__(self, result: object) -> None:
        self._result = result
        self.read_size: int | None = None
        self.closed = False

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def read(self, size: int) -> bytes:
        self.read_size = size
        if isinstance(self._result, Exception):
            raise self._result
        return cast(bytes, self._result)


def _as_binary_client(client: BinaryHttpClient) -> BinaryHttpClient:
    return client


def test_urllib_binary_client_implements_protocol() -> None:
    client = UrllibBinaryHttpClient()

    assert _as_binary_client(client) is client


@pytest.mark.parametrize("timeout", [True, 1.5, "10"])
def test_constructor_rejects_invalid_timeout_type(timeout: object) -> None:
    with pytest.raises(TypeError, match="timeout_seconds"):
        UrllibBinaryHttpClient(timeout_seconds=timeout)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout", [0, -1])
def test_constructor_rejects_non_positive_timeout(timeout: int) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        UrllibBinaryHttpClient(timeout_seconds=timeout)


@pytest.mark.parametrize("limit", [True, 1.5, "20"])
def test_constructor_rejects_invalid_size_limit_type(limit: object) -> None:
    with pytest.raises(TypeError, match="max_response_bytes"):
        UrllibBinaryHttpClient(max_response_bytes=limit)  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [0, -1])
def test_constructor_rejects_non_positive_size_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="max_response_bytes"):
        UrllibBinaryHttpClient(max_response_bytes=limit)


def test_constructor_rejects_invalid_user_agent_type() -> None:
    with pytest.raises(TypeError, match="user_agent"):
        UrllibBinaryHttpClient(user_agent=1)  # type: ignore[arg-type]


def test_constructor_rejects_blank_user_agent() -> None:
    with pytest.raises(ValueError, match="user_agent"):
        UrllibBinaryHttpClient(user_agent=" ")


def test_constructor_rejects_non_callable_opener() -> None:
    with pytest.raises(TypeError, match="opener"):
        UrllibBinaryHttpClient(opener=None)  # type: ignore[arg-type]


@pytest.mark.parametrize("url", [None, 42])
def test_get_rejects_invalid_url_type(url: object) -> None:
    with pytest.raises(TypeError, match="url"):
        UrllibBinaryHttpClient().get(url)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url",
    [
        "",
        " ",
        "ftp://lidl.cz/file",
        "https://",
        "relative/path",
    ],
)
def test_get_rejects_invalid_url_value(url: str) -> None:
    with pytest.raises(ValueError, match="url"):
        UrllibBinaryHttpClient().get(url)


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_get_returns_exact_bytes_and_uses_configuration(scheme: str) -> None:
    payload = bytes([0, 255]) + b"catalog"
    response = _Response(payload)
    captured: dict[str, object] = {}

    def opener(request: object, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return response

    client = UrllibBinaryHttpClient(
        timeout_seconds=7,
        user_agent="PriceWatch/Test",
        max_response_bytes=16,
        opener=opener,
    )

    assert client.get(f"{scheme}://lidl.cz/catalog.gz") == payload
    request = captured["request"]
    assert request.get_header("User-agent") == "PriceWatch/Test"  # type: ignore[attr-defined]
    assert captured["timeout"] == 7
    assert response.read_size == 17
    assert response.closed


def test_get_rejects_oversized_response_with_chained_cause() -> None:
    response = _Response(b"12345")
    client = UrllibBinaryHttpClient(max_response_bytes=4, opener=lambda *a, **k: response)

    with pytest.raises(HttpClientError) as captured:
        client.get("https://lidl.cz/catalog.gz")

    assert isinstance(captured.value.__cause__, ValueError)
    assert response.closed


def test_get_wraps_transport_failure_and_preserves_cause() -> None:
    failure = URLError("offline")

    def opener(*args: object, **kwargs: object) -> _Response:
        raise failure

    with pytest.raises(HttpClientError) as captured:
        UrllibBinaryHttpClient(opener=opener).get("https://lidl.cz/catalog.gz")

    assert captured.value.__cause__ is failure


def test_get_wraps_read_failure_and_closes_response() -> None:
    failure = OSError("read failed")
    response = _Response(failure)

    with pytest.raises(HttpClientError) as captured:
        UrllibBinaryHttpClient(opener=lambda *a, **k: response).get(
            "https://lidl.cz/catalog.gz"
        )

    assert captured.value.__cause__ is failure
    assert response.closed


def test_get_wraps_non_binary_response() -> None:
    response = _Response("not bytes")

    with pytest.raises(HttpClientError) as captured:
        UrllibBinaryHttpClient(opener=lambda *a, **k: response).get(
            "https://lidl.cz/catalog.gz"
        )

    assert isinstance(captured.value.__cause__, TypeError)
