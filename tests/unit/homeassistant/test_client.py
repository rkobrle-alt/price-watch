"""Tests for the standard-library Home Assistant REST client."""

import json
from collections.abc import Mapping
from contextlib import AbstractContextManager
from io import BytesIO
from typing import BinaryIO, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from infrastructure.homeassistant import (
    HomeAssistantError,
    UrllibHomeAssistantClient,
)


class RecordingResponse(AbstractContextManager[BinaryIO]):
    """Record context entry, reading and closure."""

    def __init__(self, failure: BaseException | None = None) -> None:
        """Configure an optional read failure."""
        self.failure = failure
        self.entered = False
        self.exited = False
        self.read_count = 0
        self._stream = BytesIO(b"[]")

    def __enter__(self) -> BinaryIO:
        """Enter and return this readable response."""
        self.entered = True
        return cast(BinaryIO, self)

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> None:
        """Record context exit."""
        self.exited = True

    def read(self, size: int = -1) -> bytes:
        """Read the response or raise the configured failure."""
        self.read_count += 1
        if self.failure is not None:
            raise self.failure
        return self._stream.read(size)


class RecordingOpener:
    """Capture HTTP requests and return a configured response."""

    def __init__(
        self,
        response: RecordingResponse | None = None,
        failure: BaseException | None = None,
    ) -> None:
        """Configure response or opener failure."""
        self.response = response or RecordingResponse()
        self.failure = failure
        self.calls: list[tuple[Request, int]] = []

    def __call__(
        self,
        request: Request,
        *,
        timeout: int,
    ) -> AbstractContextManager[BinaryIO]:
        """Record the call and return or raise."""
        self.calls.append((request, timeout))
        if self.failure is not None:
            raise self.failure
        return self.response


def _client(opener: object) -> UrllibHomeAssistantClient:
    return UrllibHomeAssistantClient(
        "http://supervisor/core/api/",
        "secret-token",
        timeout_seconds=7,
        user_agent="PriceWatch/Test",
        opener=cast(object, opener),
    )


def test_client_sends_exact_service_request_and_reads_response() -> None:
    response = RecordingResponse()
    opener = RecordingOpener(response)
    client = _client(opener)

    client.call_service(
        "notify",
        "send_message",
        {"title": "Parkside", "message": "Cena klesla", "entity_id": "notify.mail"},
    )

    request, timeout = opener.calls[0]
    assert request.full_url == "http://supervisor/core/api/services/notify/send_message"
    assert request.method == "POST"
    assert timeout == 7
    assert request.get_header("Authorization") == "Bearer secret-token"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("User-agent") == "PriceWatch/Test"
    assert request.data is not None
    assert request.data.decode("utf-8") == (
        '{\"entity_id\":\"notify.mail\",\"message\":\"Cena klesla\",\"title\":\"Parkside\"}'
    )
    assert json.loads(request.data) == {
        "entity_id": "notify.mail",
        "message": "Cena klesla",
        "title": "Parkside",
    }
    assert response.entered
    assert response.exited
    assert response.read_count == 1


@pytest.mark.parametrize(
    ("overrides", "exception_type"),
    [
        ({"base_url": 1}, TypeError),
        ({"base_url": " "}, ValueError),
        ({"base_url": "supervisor/core/api"}, ValueError),
        ({"base_url": "ftp://supervisor/api"}, ValueError),
        ({"base_url": "http:///core/api"}, ValueError),
        ({"base_url": "http://supervisor/api?token=x"}, ValueError),
        ({"base_url": "http://supervisor/api#fragment"}, ValueError),
        ({"access_token": 1}, TypeError),
        ({"access_token": " "}, ValueError),
        ({"timeout_seconds": True}, TypeError),
        ({"timeout_seconds": "10"}, TypeError),
        ({"timeout_seconds": 0}, ValueError),
        ({"user_agent": 1}, TypeError),
        ({"user_agent": " "}, ValueError),
        ({"opener": object()}, TypeError),
    ],
)
def test_client_rejects_invalid_constructor_values(
    overrides: dict[str, object],
    exception_type: type[Exception],
) -> None:
    values: dict[str, object] = {
        "base_url": "http://supervisor/core/api",
        "access_token": "token",
        "timeout_seconds": 10,
        "user_agent": "PriceWatch/0.12",
        "opener": RecordingOpener(),
    }
    values.update(overrides)

    with pytest.raises(exception_type):
        UrllibHomeAssistantClient(**values)


def test_client_supports_default_timeout_user_agent_and_opener() -> None:
    client = UrllibHomeAssistantClient("https://homeassistant.local/api", "token")

    assert client._timeout_seconds == 10
    assert client._user_agent == "PriceWatch/0.12"
    assert callable(client._opener)


@pytest.mark.parametrize(
    ("domain", "service", "data", "exception_type"),
    [
        (1, "send_message", {}, TypeError),
        ("Notify", "send_message", {}, ValueError),
        ("notify", 1, {}, TypeError),
        ("notify", "send-message", {}, ValueError),
        ("notify", "send_message", [], TypeError),
        ("notify", "send_message", {1: "bad"}, TypeError),
    ],
)
def test_client_rejects_invalid_service_call_values(
    domain: object,
    service: object,
    data: object,
    exception_type: type[Exception],
) -> None:
    with pytest.raises(exception_type):
        _client(RecordingOpener()).call_service(
            cast(str, domain),
            cast(str, service),
            cast(Mapping[str, object], data),
        )


def test_client_propagates_json_serialization_failure() -> None:
    with pytest.raises(TypeError):
        _client(RecordingOpener()).call_service(
            "notify",
            "send_message",
            {"invalid": object()},
        )


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError("http://example", 500, "failed", None, None),
        URLError("offline"),
        OSError("socket failed"),
    ],
)
def test_client_translates_operational_opener_failures(
    failure: Exception,
) -> None:
    client = _client(RecordingOpener(failure=failure))

    with pytest.raises(HomeAssistantError) as captured:
        client.call_service(
            "notify",
            "send_message",
            {"message": "private payload"},
        )

    assert captured.value.__cause__ is failure
    assert str(captured.value) == (
        "Home Assistant service call failed: notify.send_message"
    )
    assert "secret-token" not in str(captured.value)
    assert "private payload" not in str(captured.value)


def test_client_translates_operational_response_failure() -> None:
    failure = OSError("read failed")
    response = RecordingResponse(failure)

    with pytest.raises(HomeAssistantError) as captured:
        _client(RecordingOpener(response)).call_service("notify", "send_message", {})

    assert captured.value.__cause__ is failure
    assert response.exited


@pytest.mark.parametrize("stage", ["open", "read"])
def test_client_propagates_unexpected_failure(stage: str) -> None:
    failure = RuntimeError("bug")
    opener = (
        RecordingOpener(failure=failure)
        if stage == "open"
        else RecordingOpener(RecordingResponse(failure))
    )

    with pytest.raises(RuntimeError) as captured:
        _client(opener).call_service("notify", "send_message", {})

    assert captured.value is failure
