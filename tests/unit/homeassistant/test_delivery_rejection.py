"""Only proven pre-execution failures may be retried automatically."""

from io import BytesIO
from socket import gaierror
from urllib.error import HTTPError, URLError

import pytest

from core.notifications import NotificationDeliveryRejectedError
from infrastructure.homeassistant import UrllibHomeAssistantClient, HomeAssistantError, HomeAssistantRequestRejectedError
from infrastructure.notifications.homeassistant import HomeAssistantDailyDiscountDigestChannel
from tests.unit.homeassistant.test_digest_channel import _digest


@pytest.mark.parametrize(("failure", "rejected"), [
    (HTTPError("http://ha", 401, "private", None, None), True),
    (HTTPError("http://ha", 403, "private", None, None), True),
    (HTTPError("http://ha", 404, "private", None, None), False),
    (HTTPError("http://ha", 500, "private", None, None), False),
    (URLError(ConnectionRefusedError("private")), True),
    (gaierror("private"), True), (URLError(gaierror("private")), True),
    (TimeoutError("private"), False), (URLError(ConnectionResetError("private")), False),
])
def test_transport_classifies_before_execution_without_sensitive_data(failure, rejected) -> None:
    def opener(*args, **kwargs):
        raise failure
    client = UrllibHomeAssistantClient("http://ha/api", "token", opener=opener)
    with pytest.raises(HomeAssistantError) as captured:
        client.call_service("notify", "send_message", {})
    assert isinstance(captured.value, HomeAssistantRequestRejectedError) is rejected
    assert "private" not in str(captured.value)
    assert captured.value.__cause__ is failure


def test_failure_after_opening_request_is_ambiguous_even_for_connection_error() -> None:
    class Response(BytesIO):
        def read(self):
            raise ConnectionRefusedError("response interrupted")
    client = UrllibHomeAssistantClient("http://ha/api", "token", opener=lambda *a, **kw: Response())
    with pytest.raises(HomeAssistantError) as captured:
        client.call_service("notify", "send_message", {})
    assert not isinstance(captured.value, HomeAssistantRequestRejectedError)


def test_digest_channel_preserves_definite_rejection_type() -> None:
    class Client:
        def call_service(self, *args):
            raise HomeAssistantRequestRejectedError("rejected")
    with pytest.raises(NotificationDeliveryRejectedError):
        HomeAssistantDailyDiscountDigestChannel(Client(), "notify.test").send(_digest())
