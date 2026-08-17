"""Restart-spanning integration tests for daily digest novelty baselines."""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from applications.daily_digest import DailyDigestConfig, DailyDigestWorkflow
from core.domain import (
    Currency,
    Money,
    Percentage,
    Product,
    ProductId,
    ProviderId,
)
from core.notifications import DailyDiscountDigest, DailyDiscountDigestEngine
from core.state import StateSnapshot
from infrastructure.persistence.sqlite import (
    SqliteDailyDigestBaselineStore,
    SqliteDailyDigestReservationStore,
    SqliteStateStore,
)

_PROVIDER_ID = ProviderId(UUID("018f0000-0000-7000-8000-000000000020"))
_PRODUCT_ONE = ProductId(UUID("018f0000-0000-7000-8000-000000000001"))
_PRODUCT_TWO = ProductId(UUID("018f0000-0000-7000-8000-000000000002"))


class _Channel:
    def __init__(self) -> None:
        self.digests: list[DailyDiscountDigest] = []

    def send(self, digest: DailyDiscountDigest) -> None:
        self.digests.append(digest)


def _product(
    identifier: ProductId,
    timestamp: datetime,
    *,
    available: bool = True,
) -> Product:
    return Product(
        id=identifier,
        provider_id=_PROVIDER_ID,
        brand="PARKSIDE",
        name=f"Tool {identifier.value}",
        current_price=Money(Decimal("80"), Currency.CZK),
        original_price=Money(Decimal("100"), Currency.CZK),
        discount_percent=Percentage(Decimal("20")),
        url=f"https://example.test/{identifier.value}",
        image_url=None,
        created_at=timestamp,
        availability=available,
    )


def _save(
    path: Path,
    identifier: ProductId,
    timestamp: datetime,
    *,
    available: bool = True,
) -> None:
    SqliteStateStore(path).save(
        StateSnapshot(
            _product(identifier, timestamp, available=available),
            timestamp,
        )
    )


def _run(path: Path, timestamp: datetime) -> DailyDiscountDigest:
    channel = _Channel()
    workflow = DailyDigestWorkflow(
        SqliteStateStore(path),
        SqliteDailyDigestReservationStore(path),
        DailyDiscountDigestEngine(),
        channel,
        DailyDigestConfig(time(8), Percentage(Decimal("20"))),
        ZoneInfo("Europe/Prague"),
        baseline_store=SqliteDailyDigestBaselineStore(path),
    )
    workflow.run(timestamp)
    return channel.digests[0]


def test_baseline_survives_recomposition_and_returning_product_is_new(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    day_one = datetime(2026, 8, 8, 6, tzinfo=UTC)
    _save(path, _PRODUCT_ONE, day_one)

    first = _run(path, day_one)
    _save(path, _PRODUCT_TWO, datetime(2026, 8, 9, 5, tzinfo=UTC))
    second = _run(path, datetime(2026, 8, 9, 6, tzinfo=UTC))
    _save(
        path,
        _PRODUCT_TWO,
        datetime(2026, 8, 10, 5, tzinfo=UTC),
        available=False,
    )
    third = _run(path, datetime(2026, 8, 10, 6, tzinfo=UTC))
    _save(path, _PRODUCT_TWO, datetime(2026, 8, 11, 5, tzinfo=UTC))
    fourth = _run(path, datetime(2026, 8, 11, 6, tzinfo=UTC))

    assert first.new_product_ids == ()
    assert second.new_product_ids == (_PRODUCT_TWO,)
    assert third.new_product_ids == ()
    assert fourth.new_product_ids == (_PRODUCT_TWO,)
    assert SqliteDailyDigestBaselineStore(path).previous_product_ids(
        date(2026, 8, 12)
    ) == (_PRODUCT_ONE, _PRODUCT_TWO)
