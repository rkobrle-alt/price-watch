"""Malformed product responses remain isolated operational failures."""

from datetime import UTC, datetime
from http.client import BadStatusLine, HTTPResponse, RemoteDisconnected
from io import BytesIO
from unittest.mock import Mock

import pytest

from core.provider import ProviderTransportError
from infrastructure.http import HttpClientError, UrllibTextHttpClient
from infrastructure.providers.lidl import LidlParksideProvider
from tests.unit.providers.fixtures import LIDL_URL, SECOND_LIDL_URL, product_html
from tests.unit.providers.test_http_client import _Response

_INVALID_LINE = ";HTTP/1.1 200 OK private-response-text"


@pytest.mark.parametrize("stage", ["open", "read"])
@pytest.mark.parametrize(
    "failure", [BadStatusLine(_INVALID_LINE), RemoteDisconnected(_INVALID_LINE)],
)
def test_malformed_response_preserves_cause_without_retry_or_raw_text(
    monkeypatch: pytest.MonkeyPatch, stage: str, failure: BadStatusLine,
) -> None:
    opener = Mock()
    if stage == "open":
        opener.side_effect = failure
    else:
        opener.return_value = _Response(b"", None)
        monkeypatch.setattr(
            opener.return_value, "read", Mock(side_effect=failure),
        )
    monkeypatch.setattr("infrastructure.http.urllib_client.urlopen", opener)

    with pytest.raises(HttpClientError) as captured:
        UrllibTextHttpClient().get(LIDL_URL)

    assert str(captured.value) == f"failed to retrieve {LIDL_URL} [HTTP protocol error]"
    assert captured.value.__cause__ is failure
    assert _INVALID_LINE not in str(captured.value)
    assert opener.call_count == 1


def test_real_malformed_status_line_does_not_block_next_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket = Mock()
    socket.makefile.return_value = BytesIO(b";HTTP/1.1 200 OK\r\n\r\n")
    response = HTTPResponse(socket)
    calls = 0

    def open_response(*args: object, **kwargs: object) -> _Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            response.begin()
        return _Response(product_html().encode(), "utf-8")

    monkeypatch.setattr("infrastructure.http.urllib_client.urlopen", open_response)
    try:
        result = LidlParksideProvider(
            (LIDL_URL, SECOND_LIDL_URL), UrllibTextHttpClient(),
            lambda: datetime(2026, 9, 9, tzinfo=UTC),
        ).fetch()
    finally:
        response.close()

    assert calls == 2
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], ProviderTransportError)
    assert str(result.errors[0]) == (
        f"{LIDL_URL}: failed to retrieve {LIDL_URL} [HTTP protocol error]"
    )
    assert len(result.products) == 1
    assert result.products[0].url == SECOND_LIDL_URL


def test_unrelated_programming_error_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("programming failure")
    opener = Mock(side_effect=failure)
    monkeypatch.setattr("infrastructure.http.urllib_client.urlopen", opener)
    with pytest.raises(RuntimeError) as captured:
        UrllibTextHttpClient().get(LIDL_URL)
    assert captured.value is failure
    assert opener.call_count == 1
