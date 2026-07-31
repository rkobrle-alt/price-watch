"""End-to-end configured watch execution with durable state."""

import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest

from applications.cli import run
from infrastructure.configuration.toml import TomlConfigurationLoader
from infrastructure.http import UrllibTextHttpClient

PRODUCT_URL = "https://www.lidl.cz/parkside-config-test/p400"
TIMESTAMP = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


class RecordingDelay:
    """Record configured intervals without real waiting."""

    def __init__(self) -> None:
        """Create an empty record."""
        self.durations: list[timedelta] = []

    def wait(self, duration: timedelta) -> None:
        """Record one wait."""
        self.durations.append(duration)


class NotificationIds:
    """Supply deterministic identifiers for two rules and cycles."""

    def __init__(self) -> None:
        """Create four deterministic UUID values."""
        self._values = iter(
            UUID(f"92000000-0000-4000-8000-{index:012d}")
            for index in range(1, 5)
        )

    def __call__(self) -> UUID:
        """Return the next identifier."""
        return next(self._values)


def _page(*, price: str, availability: str) -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "sku": "PARKSIDE-CONFIG-400",
        "name": "Parkside Configured Tool",
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


def test_toml_configured_watch_reuses_relative_json_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = iter(
        (
            _page(price="100.00", availability="OutOfStock"),
            _page(price="75.00", availability="InStock"),
        )
    )

    def fake_get(client: UrllibTextHttpClient, url: str) -> str:
        assert url == PRODUCT_URL
        return next(pages)

    monkeypatch.setattr(UrllibTextHttpClient, "get", fake_get)
    config_directory = tmp_path / "configuration"
    config_directory.mkdir()
    config_file = config_directory / "price-watch.toml"
    config_file.write_text(
        "\n".join(
            (
                "schema_version = 1",
                "",
                "[provider.lidl]",
                f'product_urls = ["{PRODUCT_URL}"]',
                "timeout_seconds = 7",
                "",
                "[state]",
                'file = "data/state.json"',
                "",
                "[rules.price_drop]",
                'percentage = "10.00"',
                'fixed_amount = "5.00"',
                "",
                "[scheduler]",
                "interval_seconds = 30",
                "",
            )
        ),
        encoding="utf-8",
    )
    stdout = StringIO()
    stderr = StringIO()
    delay = RecordingDelay()

    status = run(
        (
            "watch",
            "--config",
            str(config_file),
            "--max-cycles",
            "2",
        ),
        stdout,
        stderr,
        lambda: TIMESTAMP,
        NotificationIds(),
        delay=delay,
        configuration_loader=TomlConfigurationLoader(),
    )

    assert status == 0
    assert delay.durations == [timedelta(seconds=30)]
    assert stdout.getvalue().count("sync complete:") == 2
    assert "Product price decreased." in stdout.getvalue()
    assert "Product is back in stock." in stdout.getvalue()
    assert stderr.getvalue() == ""
    state_file = config_directory / "data" / "state.json"
    document = json.loads(state_file.read_text(encoding="utf-8"))
    stored_product = next(iter(document["snapshots"].values()))["product"]
    assert stored_product["current_price"]["amount"] == "75.00"
    assert stored_product["availability"] is True
