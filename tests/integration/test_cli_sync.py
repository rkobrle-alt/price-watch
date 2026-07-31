"""Full command integration for durable Lidl synchronization."""

import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest

from applications.cli import run
from infrastructure.http import UrllibTextHttpClient

PRODUCT_URL = "https://www.lidl.cz/parkside-cli-test/p200"
TIMESTAMP = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


class NotificationIds:
    """Return deterministic identifiers for two rules across two runs."""

    def __init__(self) -> None:
        """Create the expected four-value sequence."""
        self._values = iter(
            UUID(f"90000000-0000-4000-8000-{index:012d}")
            for index in range(1, 5)
        )

    def __call__(self) -> UUID:
        """Return the next identifier."""
        return next(self._values)


def _page(*, price: str, availability: str) -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "sku": "PARKSIDE-CLI-200",
        "name": "Parkside CLI Tool",
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


def _argv(state_file: Path) -> tuple[str, ...]:
    return (
        "sync",
        "--url",
        PRODUCT_URL,
        "--state-file",
        str(state_file),
        "--price-drop-percentage",
        "10.00",
        "--price-drop-amount",
        "5.00",
    )


def test_cli_second_run_detects_durable_lidl_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_page = {
        "content": _page(price="100.00", availability="OutOfStock")
    }

    def fake_get(client: UrllibTextHttpClient, url: str) -> str:
        assert url == PRODUCT_URL
        return current_page["content"]

    monkeypatch.setattr(UrllibTextHttpClient, "get", fake_get)
    state_file = tmp_path / "state" / "products.json"
    notification_ids = NotificationIds()
    first_stdout = StringIO()
    first_stderr = StringIO()

    first_status = run(
        _argv(state_file),
        first_stdout,
        first_stderr,
        lambda: TIMESTAMP,
        notification_ids,
    )

    assert first_status == 0
    assert "notifications=0" in first_stdout.getvalue()
    assert first_stderr.getvalue() == ""
    assert state_file.is_file()

    current_page["content"] = _page(price="80.00", availability="InStock")
    second_stdout = StringIO()
    second_stderr = StringIO()

    second_status = run(
        _argv(state_file),
        second_stdout,
        second_stderr,
        lambda: TIMESTAMP,
        notification_ids,
    )

    assert second_status == 0
    assert "Product price decreased." in second_stdout.getvalue()
    assert "Product is back in stock." in second_stdout.getvalue()
    assert "notifications=2" in second_stdout.getvalue()
    assert second_stderr.getvalue() == ""
    document = json.loads(state_file.read_text(encoding="utf-8"))
    stored_product = next(iter(document["snapshots"].values()))["product"]
    assert stored_product["current_price"]["amount"] == "80.00"
    assert stored_product["availability"] is True
