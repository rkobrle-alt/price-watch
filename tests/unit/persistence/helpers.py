"""Deterministic fixtures for JSON persistence tests."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from core.domain import Currency, Money, Percentage, Product, ProductId, ProviderId
from core.state import StateSnapshot
from infrastructure.persistence.json.codec import create_document, encode_snapshot

PRODUCT_ID = ProductId(UUID("018f0000-0000-7000-8000-000000000001"))
OTHER_PRODUCT_ID = ProductId(UUID("018f0000-0000-7000-8000-000000000002"))
PROVIDER_ID = ProviderId(UUID("018f0000-0000-7000-8000-000000000010"))
PRODUCT_TIME = datetime(
    2026,
    7,
    31,
    9,
    30,
    15,
    123456,
    tzinfo=timezone(timedelta(hours=2)),
)
SNAPSHOT_TIME = datetime(
    2026,
    7,
    31,
    10,
    45,
    30,
    654321,
    tzinfo=timezone(timedelta(hours=-4)),
)


def create_snapshot(
    *,
    product_id: ProductId = PRODUCT_ID,
    amount: str = "199.9900",
    timestamp: datetime = SNAPSHOT_TIME,
    original_price: Money | None = Money(Decimal("249.9900"), Currency.EUR),
    image_url: str | None = "https://example.test/tool.jpg",
    availability: bool = False,
) -> StateSnapshot:
    """Create a snapshot containing every optional Product field."""
    product = Product(
        id=product_id,
        provider_id=PROVIDER_ID,
        brand="PARKSIDE PERFORMANCE®",
        name="Aku nářadí",
        current_price=Money(Decimal(amount), Currency.EUR),
        original_price=original_price,
        discount_percent=Percentage(Decimal("20.0040")),
        url="https://www.lidl.cz/p/tool/p100000001",
        image_url=image_url,
        created_at=PRODUCT_TIME,
        availability=availability,
    )
    return StateSnapshot(product, timestamp)


def create_document_with(snapshot: StateSnapshot) -> dict[str, object]:
    """Create a schema-v1 document containing one encoded snapshot."""
    document = create_document()
    snapshots = document["snapshots"]
    assert isinstance(snapshots, dict)
    snapshots[str(snapshot.product.id.value)] = encode_snapshot(snapshot)
    return document


def write_json(path: Path, document: object) -> None:
    """Write a JSON test fixture as UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
