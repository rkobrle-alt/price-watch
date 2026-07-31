"""Full command integration for scheduled durable synchronization."""

import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest

from applications.cli import run
from infrastructure.http import UrllibTextHttpClient

PRODUCT_URL = "https://www.lidl.cz/parkside-watch-test/p300"
TIMESTAMP = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


class RecordingDelay:
    """Record scheduled waits without blocking the integration test."""

    def __init__(self) -> None:
        """Create an empty duration record."""
        self.durations: list[timedelta] = []

    def wait(self, duration: timedelta) -> None:
        """Record one requested interval."""
        self.durations.append(duration)


class NotificationIds:
    """Return deterministic identifiers for two scheduled cycles."""

    def __init__(self) -> None:
        """Create four IDs for two rules evaluated twice."""
        self._values = iter(
            UUID(f"91000000-0000-4000-8000-{index:012d}")
            for index in range(1, 5)
        )

    def __call__(self) -> UUID:
        """Return the next identifier."""
        return next(self._values)


def _page(*, price: str, availability: str) -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "sku": "PARKSIDE-WATCH-300",
        "name": "Parkside Scheduled Tool",
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


def test_watch_reuses_json_state_between_scheduled_cycles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = iter(
        (
            _page(price="100.00", availability="OutOfStock"),
            _page(price="80.00", availability="InStock"),
        )
    )

    def fake_get(client: UrllibTextHttpClient, url: str) -> str:
        assert url == PRODUCT_URL
        return next(pages)

    monkeypatch.setattr(UrllibTextHttpClient, "get", fake_get)
    state_file = tmp_path / "state" / "products.json"
    stdout = StringIO()
    stderr = StringIO()
    delay = RecordingDelay()

    status = run(
        (
            "watch",
            "--url",
            PRODUCT_URL,
            "--state-file",
            str(state_file),
            "--interval-seconds",
            "30",
            "--max-cycles",
            "2",
            "--price-drop-percentage",
            "10.00",
        ),
        stdout,
        stderr,
        lambda: TIMESTAMP,
        NotificationIds(),
        delay=delay,
    )

    assert status == 0
    assert delay.durations == [timedelta(seconds=30)]
    assert stdout.getvalue().count("sync complete:") == 2
    assert "Product price decreased." in stdout.getvalue()
    assert "Product is back in stock." in stdout.getvalue()
    assert stdout.getvalue().endswith(
        "watch complete: cycles=2 provider_error_cycles=0\n"
    )
    assert stderr.getvalue() == ""
    document = json.loads(state_file.read_text(encoding="utf-8"))
    stored_product = next(iter(document["snapshots"].values()))["product"]
    assert stored_product["current_price"]["amount"] == "80.00"
    assert stored_product["availability"] is True
