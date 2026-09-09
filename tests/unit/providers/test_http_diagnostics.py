"""Safe HTTP failure details survive the provider's existing error boundary."""

from datetime import UTC, datetime
from email.message import Message
from http.client import IncompleteRead
from io import BytesIO
from socket import gaierror
from ssl import SSLError
from urllib.error import HTTPError, URLError

import pytest

from core.provider import ProviderTransportError
from infrastructure.http import HttpClientError, UrllibTextHttpClient
from infrastructure.providers.lidl import LidlParksideProvider

_URL = "https://www.lidl.cz/p/parkside-test/p100324645"
_SECRET = "private-response-and-token"


@pytest.mark.parametrize(
    ("failure", "detail"),
    [
        (TimeoutError(_SECRET), "timeout"),
        (URLError(TimeoutError(_SECRET)), "timeout"),
        (gaierror(_SECRET), "DNS error"),
        (URLError(gaierror(_SECRET)), "DNS error"),
        (SSLError(_SECRET), "TLS error"),
        (URLError(SSLError(_SECRET)), "TLS error"),
        (ConnectionResetError(_SECRET), "connection error"),
        (URLError(ConnectionRefusedError(_SECRET)), "connection error"),
        (URLError(_SECRET), "network error"),
        (URLError(OSError(_SECRET)), "network error"),
        (UnicodeError(_SECRET), "decoding error"),
        (OSError(_SECRET), "I/O error"),
    ],
)
def test_failure_details_preserve_cause_without_retry_or_sensitive_text(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, detail: str,
) -> None:
    calls = 0

    def fail(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise failure

    monkeypatch.setattr("infrastructure.http.urllib_client.urlopen", fail)
    with pytest.raises(HttpClientError) as captured:
        UrllibTextHttpClient().get(_URL)
    assert str(captured.value) == f"failed to retrieve {_URL} [{detail}]"
    assert captured.value.__cause__ is failure
    assert _SECRET not in str(captured.value)
    assert calls == 1


@pytest.mark.parametrize("status", [404, 429, 503])
def test_http_status_reaches_provider_without_response_data_or_retry(
    monkeypatch: pytest.MonkeyPatch, status: int,
) -> None:
    headers = Message()
    headers["X-Private"] = _SECRET
    failure = HTTPError(_URL, status, _SECRET, headers, BytesIO(_SECRET.encode()))
    calls = 0

    def fail(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise failure

    monkeypatch.setattr("infrastructure.http.urllib_client.urlopen", fail)
    try:
        with pytest.raises(HttpClientError) as captured:
            UrllibTextHttpClient().get(_URL)
        assert captured.value.__cause__ is failure
        assert str(captured.value) == f"failed to retrieve {_URL} [HTTP {status}]"
        assert calls == 1
        result = LidlParksideProvider(
            (_URL,), UrllibTextHttpClient(), lambda: datetime(2026, 9, 9, tzinfo=UTC),
        ).fetch()
        assert result.products == ()
        assert len(result.errors) == 1
        assert isinstance(result.errors[0], ProviderTransportError)
        assert str(result.errors[0]) == f"{_URL}: failed to retrieve {_URL} [HTTP {status}]"
        assert _SECRET not in str(result.errors[0])
        assert calls == 2
    finally:
        failure.close()


def test_incomplete_read_detail_preserves_two_attempt_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = IncompleteRead(_SECRET.encode(), 100)
    calls = 0

    def fail(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise failure

    monkeypatch.setattr("infrastructure.http.urllib_client.urlopen", fail)
    with pytest.raises(HttpClientError) as captured:
        UrllibTextHttpClient().get(_URL)
    assert str(captured.value) == (
        f"failed to retrieve {_URL} [incomplete response after 2 attempts]"
    )
    assert captured.value.__cause__ is failure
    assert calls == 2
