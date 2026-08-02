"""Boundary integration test for the complete Home Assistant App runtime."""

import importlib
import json

import pytest
from contextlib import AbstractContextManager
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, cast
from urllib.request import Request
from uuid import uuid4

from applications.homeassistant import run
from infrastructure.configuration.json import JsonConfigurationLoader
from infrastructure.homeassistant import UrllibHomeAssistantClient
from tests.unit.homeassistant_app.helpers import (
    PRODUCT_URL,
    TIMESTAMP,
    RecordingDelay,
    RecordingStream,
)

composition_module = importlib.import_module("applications.homeassistant.composition")


class SequencedTextClient:
    """Return a different Lidl page for each scheduled cycle."""

    def __init__(self, pages: tuple[str, ...]) -> None:
        """Configure ordered page bodies."""
        self._pages = iter(pages)
        self.requested_urls: list[str] = []

    def get(self, url: str) -> str:
        """Return the next page without network access."""
        self.requested_urls.append(url)
        return next(self._pages)


class SuccessfulResponse(AbstractContextManager[BinaryIO]):
    """Provide a readable successful Home Assistant response."""

    def __init__(self) -> None:
        """Create an empty JSON response."""
        self._body = BytesIO(b"[]")

    def __enter__(self) -> BinaryIO:
        """Return this readable response."""
        return cast(BinaryIO, self)

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> None:
        """Complete the response context."""

    def read(self, size: int = -1) -> bytes:
        """Read the response body."""
        return self._body.read(size)


class CapturingOpener:
    """Capture Home Assistant REST requests."""

    def __init__(self) -> None:
        """Initialize empty request storage."""
        self.requests: list[tuple[Request, int]] = []

    def __call__(
        self,
        request: Request,
        *,
        timeout: int,
    ) -> AbstractContextManager[BinaryIO]:
        """Record one request and return success."""
        self.requests.append((request, timeout))
        return SuccessfulResponse()


def _page(*, price: str, availability: str) -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "sku": "PARKSIDE-HA-100",
        "name": "Parkside Home Assistant Tool",
        "brand": {"@type": "Brand", "name": "PARKSIDE"},
        "offers": {
            "@type": "Offer",
            "price": price,
            "priceCurrency": "CZK",
            "availability": f"https://schema.org/{availability}",
        },
    }
    return (
        '<html><script type="application/ld+json">'
        f"{json.dumps(product)}"
        "</script></html>"
    )


def test_app_persists_baseline_then_delivers_detected_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patcher = cast(object, monkeypatch)
    options_path = tmp_path / "options.json"
    options_path.write_text(
        json.dumps(
            {
                "product_urls": [PRODUCT_URL],
                "notify_entity": "notify.gmail_parkside",
                "interval_seconds": 60,
                "timeout_seconds": 8,
                "price_drop_percentage": "10.00",
                "notification_title": "Parkside Price Watch",
            }
        ),
        encoding="utf-8",
    )
    options = JsonConfigurationLoader().load(options_path)
    text_client = SequencedTextClient(
        (
            _page(price="100.00", availability="OutOfStock"),
            _page(price="80.00", availability="InStock"),
        )
    )
    opener = CapturingOpener()
    original_client = UrllibHomeAssistantClient

    monkeypatch.setattr(
        composition_module,
        "UrllibTextHttpClient",
        lambda **keywords: text_client,
    )
    monkeypatch.setattr(
        composition_module,
        "UrllibHomeAssistantClient",
        lambda base_url, access_token, timeout_seconds, user_agent: original_client(
            base_url,
            access_token,
            timeout_seconds,
            user_agent,
            opener=opener,
        ),
    )
    stdout = RecordingStream()
    stderr = RecordingStream()
    delay = RecordingDelay()

    status = run(
        options,
        "supervisor-token",
        stdout,
        stderr,
        lambda: TIMESTAMP,
        uuid4,
        delay,
        data_directory=tmp_path,
        max_cycles=2,
    )

    assert status == 0
    assert text_client.requested_urls == [PRODUCT_URL, PRODUCT_URL]
    assert delay.durations[0].total_seconds() == 60
    assert (tmp_path / "state.json").is_file()
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    snapshot = next(iter(state["snapshots"].values()))
    assert snapshot["product"]["current_price"]["amount"] == "80.00"
    assert snapshot["product"]["availability"] is True
    assert len(opener.requests) == 2
    payloads = []
    for request, timeout in opener.requests:
        assert request.full_url == (
            "http://supervisor/core/api/services/notify/send_message"
        )
        assert request.get_header("Authorization") == "Bearer supervisor-token"
        assert timeout == 8
        assert request.data is not None
        payloads.append(json.loads(request.data))
    assert [payload["entity_id"] for payload in payloads] == [
        "notify.gmail_parkside",
        "notify.gmail_parkside",
    ]
    assert [payload["message"].splitlines()[0] for payload in payloads] == [
        "Product price decreased.",
        "Product is back in stock.",
    ]
    assert stdout.text.count("sync complete:") == 2
    assert stderr.text == ""
