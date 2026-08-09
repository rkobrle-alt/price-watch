"""Integration test for Home Assistant catalog monitoring composition."""

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO, cast
from uuid import uuid4

import pytest

from applications.homeassistant import run
from core.catalog import ProductReference
from infrastructure.homeassistant import UrllibHomeAssistantClient
from infrastructure.providers.lidl import LidlParksideProvider
from tests.integration.test_homeassistant_app import CapturingOpener, _page
from tests.unit.persistence.sqlite_helpers import open_database
from tests.unit.homeassistant_app.helpers import (
    RecordingDelay,
    RecordingStream,
    TIMESTAMP,
)

_composition = importlib.import_module("applications.homeassistant.composition")
_FIRST_URL = "https://www.lidl.cz/p/parkside-first/p100"
_SECOND_URL = "https://www.lidl.cz/p/parkside-second/p200"


class _Catalog:
    id = LidlParksideProvider.id
    calls = 0

    def __init__(self, http_client: object) -> None:
        self._http_client = http_client

    def discover(self) -> tuple[ProductReference, ...]:
        type(self).calls += 1
        return (
            ProductReference(self.id, "p100", _FIRST_URL),
            ProductReference(self.id, "p200", _SECOND_URL),
        )


class _TextClient:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str) -> str:
        self.urls.append(url)
        return _page(price="100.00", availability="InStock")


class _SingleCatalog(_Catalog):
    def discover(self) -> tuple[ProductReference, ...]:
        type(self).calls += 1
        return (ProductReference(self.id, "p100", _FIRST_URL),)


class _ChangingTextClient:
    def __init__(self) -> None:
        self._prices = iter(("100.00", "80.00", "80.00"))

    def get(self, url: str) -> str:
        return _page(price=next(self._prices), availability="InStock")


class _DigestChangingTextClient:
    def __init__(self) -> None:
        self._prices = iter(("100.00", "80.00", "80.00"))

    def get(self, url: str) -> str:
        return _page(price=next(self._prices), availability="InStock")


def test_catalog_mode_discovers_and_rotates_durable_batches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _Catalog.calls = 0
    text_client = _TextClient()
    opener = CapturingOpener()
    original_client = UrllibHomeAssistantClient
    monkeypatch.setattr(_composition, "LidlParksideCatalog", _Catalog)
    monkeypatch.setattr(
        _composition,
        "UrllibBinaryHttpClient",
        lambda **keywords: object(),
    )
    monkeypatch.setattr(
        _composition,
        "UrllibTextHttpClient",
        lambda **keywords: text_client,
    )
    monkeypatch.setattr(
        _composition,
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

    status = run(
        {
            "catalog_enabled": True,
            "notify_entity": "notify.gmail_parkside",
            "interval_seconds": 60,
            "timeout_seconds": 8,
            "catalog_batch_size": 1,
            "catalog_discovery_interval_cycles": 2,
        },
        "supervisor-token",
        cast(TextIO, stdout),
        cast(TextIO, stderr),
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        data_directory=tmp_path,
        max_cycles=2,
    )

    assert status == 0
    assert _Catalog.calls == 1
    assert text_client.urls == [_FIRST_URL, _SECOND_URL]
    database = tmp_path / "catalog.sqlite3"
    assert database.is_file()
    with open_database(database) as connection:
        catalog_count = connection.execute(
            "SELECT COUNT(*) FROM catalog_entries"
        ).fetchone()
        attempted_count = connection.execute(
            "SELECT COUNT(*) FROM catalog_entries "
            "WHERE last_refresh_attempt_at IS NOT NULL"
        ).fetchone()
        observation_count = connection.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()
        version = connection.execute("PRAGMA user_version").fetchone()
    assert catalog_count == (2,)
    assert attempted_count == (2,)
    assert observation_count == (2,)
    assert version == (4,)
    assert stdout.text.count("catalog sync complete:") == 2
    assert "selected=1" in stdout.text
    assert stderr.text == ""

    status_requests = [
        request
        for request, _ in opener.requests
        if "/states/sensor.price_watch_status" in request.full_url
    ]
    assert len(status_requests) == 2
    for request in status_requests:
        assert request.data is not None
        assert json.loads(request.data)["state"] == "ok"
    for entity_id in (
        "sensor.price_watch_discounted_products",
        "sensor.price_watch_catalog_errors",
        "sensor.price_watch_last_checked",
        "sensor.price_watch_catalog",
    ):
        requests = [
            request
            for request, _ in opener.requests
            if request.full_url.endswith(f"/states/{entity_id}")
        ]
        assert len(requests) == 2


def test_catalog_alerts_once_for_repeated_twenty_percent_price(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _SingleCatalog.calls = 0
    text_client = _ChangingTextClient()
    opener = CapturingOpener()
    original_client = UrllibHomeAssistantClient
    monkeypatch.setattr(_composition, "LidlParksideCatalog", _SingleCatalog)
    monkeypatch.setattr(
        _composition,
        "UrllibBinaryHttpClient",
        lambda **keywords: object(),
    )
    monkeypatch.setattr(
        _composition,
        "UrllibTextHttpClient",
        lambda **keywords: text_client,
    )
    monkeypatch.setattr(
        _composition,
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

    status = run(
        {
            "catalog_enabled": True,
            "notify_entity": "notify.gmail_parkside",
            "interval_seconds": 60,
            "catalog_batch_size": 1,
            "catalog_discovery_interval_cycles": 10,
        },
        "supervisor-token",
        cast(TextIO, stdout),
        cast(TextIO, RecordingStream()),
        lambda: TIMESTAMP,
        uuid4,
        RecordingDelay(),
        data_directory=tmp_path,
        max_cycles=3,
    )

    assert status == 0
    notification_requests = [
        request
        for request, _ in opener.requests
        if "/services/notify/send_message" in request.full_url
    ]
    assert len(notification_requests) == 1
    assert notification_requests[0].data is not None
    message = json.loads(notification_requests[0].data)["message"]
    assert "Reference price: 100.00 CZK" in message
    assert "Discount: 20%" in message
    with open_database(tmp_path / "catalog.sqlite3") as connection:
        reservation_count = connection.execute(
            "SELECT COUNT(*) FROM notification_reservations"
        ).fetchone()
        observation_count = connection.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()
    assert reservation_count == (1,)
    assert observation_count == (3,)
    assert stdout.text.count(" notifications=1 suppressed_notifications=") == 1
    assert stdout.text.count("suppressed_notifications=1") == 1
    overview_payloads = [
        json.loads(request.data)
        for request, _ in opener.requests
        if "/states/sensor.price_watch_discounted_products" in request.full_url
        and request.data is not None
    ]
    assert [payload["state"] for payload in overview_payloads] == ["0", "1", "1"]
    assert [
        payload["attributes"]["notification_count"]
        for payload in overview_payloads
    ] == [0, 1, 0]
    assert [
        payload["attributes"]["suppressed_notification_count"]
        for payload in overview_payloads
    ] == [0, 0, 1]


def test_daily_digest_sends_once_after_local_time_across_recomposition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _SingleCatalog.calls = 0
    text_client = _DigestChangingTextClient()
    opener = CapturingOpener()
    original_client = UrllibHomeAssistantClient
    monkeypatch.setattr(_composition, "LidlParksideCatalog", _SingleCatalog)
    monkeypatch.setattr(
        _composition,
        "UrllibBinaryHttpClient",
        lambda **keywords: object(),
    )
    monkeypatch.setattr(
        _composition,
        "UrllibTextHttpClient",
        lambda **keywords: text_client,
    )
    monkeypatch.setattr(
        _composition,
        "UrllibHomeAssistantClient",
        lambda base_url, access_token, timeout_seconds, user_agent: original_client(
            base_url,
            access_token,
            timeout_seconds,
            user_agent,
            opener=opener,
        ),
    )
    options = {
        "catalog_enabled": True,
        "notify_entity": "notify.gmail_parkside",
        "notification_title": "Parkside",
        "interval_seconds": 60,
        "catalog_batch_size": 1,
        "catalog_discovery_interval_cycles": 10,
        "daily_digest_enabled": True,
        "daily_digest_time": "08:00",
        "individual_notifications_enabled": False,
    }
    outputs: list[RecordingStream] = []

    for timestamp in (
        datetime(2026, 8, 8, 5, 0, tzinfo=UTC),
        datetime(2026, 8, 8, 6, 0, tzinfo=UTC),
        datetime(2026, 8, 8, 7, 0, tzinfo=UTC),
    ):
        stdout = RecordingStream()
        outputs.append(stdout)
        assert run(
            options,
            "supervisor-token",
            cast(TextIO, stdout),
            cast(TextIO, RecordingStream()),
            lambda timestamp=timestamp: timestamp,
            uuid4,
            RecordingDelay(),
            data_directory=tmp_path,
            max_cycles=1,
        ) == 0

    notification_payloads = [
        json.loads(request.data)
        for request, _ in opener.requests
        if "/services/notify/send_message" in request.full_url
        and request.data is not None
    ]
    digest_payloads = [
        payload
        for payload in notification_payloads
        if payload["title"] == "Parkside Daily Digest"
    ]
    assert len(digest_payloads) == 1
    assert notification_payloads == digest_payloads
    assert "Discounted products: 1" in digest_payloads[0]["message"]
    assert "Reference price: 100.00 CZK" in digest_payloads[0]["message"]
    assert "digest_status=not_due" in outputs[0].text
    assert "digest_status=sent digest_products=1" in outputs[1].text
    assert "digest_status=already_sent" in outputs[2].text
    with open_database(tmp_path / "catalog.sqlite3") as connection:
        assert connection.execute(
            "SELECT calendar_date FROM daily_digest_reservations"
        ).fetchall() == [("2026-08-08",)]
        assert connection.execute(
            "SELECT COUNT(*) FROM notification_reservations"
        ).fetchone() == (0,)
