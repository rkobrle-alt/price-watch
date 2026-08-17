"""Tests for calendar-based daily digest orchestration."""

import inspect
from datetime import UTC, date, datetime, time, timezone
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

import pytest

import applications.daily_digest as digest_api
from applications.daily_digest import (
    DailyDigestConfig,
    DailyDigestResult,
    DailyDigestStatus,
    DailyDigestWorkflow,
)
from core.domain import Percentage
from core.notifications import (
    DailyDigestBaselineStore,
    DailyDiscountDigest,
    DailyDiscountDigestChannel,
    DailyDiscountDigestEngine,
    DailyDigestReservationStore,
)
from core.promotions import DailyPromotion, DailyPromotionSource, PromotionError
from core.state import LatestSnapshotReader, StateSnapshot

_PRAGUE = ZoneInfo("Europe/Prague")
_DATE = date(2026, 8, 8)
_TIMESTAMP = datetime(2026, 8, 8, 6, 0, tzinfo=UTC)


class _Reader:
    def __init__(self, snapshots: tuple[StateSnapshot, ...] = ()) -> None:
        self.snapshots: object = snapshots
        self.calls = 0
        self.error: Exception | None = None

    def latest_snapshots(self) -> tuple[StateSnapshot, ...]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return cast(tuple[StateSnapshot, ...], self.snapshots)


class _Reservations:
    def __init__(self, reserved: bool = True) -> None:
        self.reserved = reserved
        self.reserve_calls: list[tuple[date, datetime]] = []
        self.release_calls: list[date] = []
        self.release_error: Exception | None = None

    def reserve(self, calendar_date: date, reserved_at: datetime) -> bool:
        self.reserve_calls.append((calendar_date, reserved_at))
        return self.reserved

    def release(self, calendar_date: date) -> None:
        self.release_calls.append(calendar_date)
        if self.release_error is not None:
            raise self.release_error


class _Channel:
    def __init__(self) -> None:
        self.digests: list[DailyDiscountDigest] = []
        self.error: Exception | None = None

    def send(self, digest: DailyDiscountDigest) -> None:
        if self.error is not None:
            raise self.error
        self.digests.append(digest)


class _Baselines:
    def __init__(self, previous: object = None) -> None:
        self.previous = previous
        self.previous_calls: list[date] = []
        self.stage_calls: list[tuple[date, tuple[object, ...]]] = []
        self.release_calls: list[date] = []
        self.error: Exception | None = None
        self.release_error: Exception | None = None

    def previous_product_ids(self, calendar_date: date) -> object:
        self.previous_calls.append(calendar_date)
        if self.error is not None:
            raise self.error
        return self.previous

    def stage(
        self,
        calendar_date: date,
        product_ids: tuple[object, ...],
    ) -> None:
        self.stage_calls.append((calendar_date, product_ids))
        if self.error is not None:
            raise self.error

    def release(self, calendar_date: date) -> None:
        self.release_calls.append(calendar_date)
        if self.release_error is not None:
            raise self.release_error


class _PromotionSource:
    def __init__(self, value: object = None) -> None:
        self.value = value
        self.calls = 0
        self.error: Exception | None = None

    def current(self) -> DailyPromotion | None:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return cast(DailyPromotion | None, self.value)


class _WrongEngine(DailyDiscountDigestEngine):
    def generate(self, *args: object, **kwargs: object) -> DailyDiscountDigest:
        return cast(DailyDiscountDigest, object())


def _workflow(
    reader: _Reader | None = None,
    reservations: _Reservations | None = None,
    channel: _Channel | None = None,
    *,
    engine: DailyDiscountDigestEngine | None = None,
    delivery_time: time = time(8, 0),
    promotion_source: _PromotionSource | None = None,
    baseline_store: _Baselines | None = None,
) -> DailyDigestWorkflow:
    return DailyDigestWorkflow(
        cast(LatestSnapshotReader, reader or _Reader()),
        cast(DailyDigestReservationStore, reservations or _Reservations()),
        engine or DailyDiscountDigestEngine(),
        cast(DailyDiscountDigestChannel, channel or _Channel()),
        DailyDigestConfig(delivery_time, Percentage(Decimal("20"))),
        _PRAGUE,
        promotion_source=cast(
            DailyPromotionSource | None,
            promotion_source,
        ),
        baseline_store=cast(
            DailyDigestBaselineStore | None,
            baseline_store,
        ),
    )


def test_before_local_delivery_time_has_no_side_effects() -> None:
    reader = _Reader()
    reservations = _Reservations()
    channel = _Channel()
    source = _PromotionSource(DailyPromotion("Offer"))

    result = _workflow(
        reader,
        reservations,
        channel,
        promotion_source=source,
    ).run(
        datetime(2026, 8, 8, 5, 59, tzinfo=UTC)
    )

    assert result == DailyDigestResult(_DATE, DailyDigestStatus.NOT_DUE)
    assert reader.calls == 0
    assert reservations.reserve_calls == []
    assert channel.digests == []
    assert source.calls == 0


def test_exact_local_time_sends_empty_digest() -> None:
    reservations = _Reservations()
    channel = _Channel()

    result = _workflow(reservations=reservations, channel=channel).run(_TIMESTAMP)

    assert result == DailyDigestResult(_DATE, DailyDigestStatus.SENT, 0)
    assert reservations.reserve_calls == [(_DATE, _TIMESTAMP)]
    assert len(channel.digests) == 1
    assert channel.digests[0].calendar_date == _DATE


def test_due_digest_reads_and_stages_baseline_before_delivery() -> None:
    baseline = _Baselines(())
    channel = _Channel()

    result = _workflow(channel=channel, baseline_store=baseline).run(_TIMESTAMP)

    assert result.status is DailyDigestStatus.SENT
    assert baseline.previous_calls == [_DATE]
    assert baseline.stage_calls == [(_DATE, ())]
    assert baseline.release_calls == []


def test_existing_date_suppresses_query_and_delivery() -> None:
    reader = _Reader()
    reservations = _Reservations(False)
    channel = _Channel()
    source = _PromotionSource(DailyPromotion("Offer"))
    baseline = _Baselines(())

    result = _workflow(
        reader,
        reservations,
        channel,
        promotion_source=source,
        baseline_store=baseline,
    ).run(_TIMESTAMP)

    assert result == DailyDigestResult(_DATE, DailyDigestStatus.ALREADY_SENT)
    assert reader.calls == 0
    assert channel.digests == []
    assert source.calls == 0
    assert baseline.previous_calls == []
    assert baseline.stage_calls == []


def test_promotion_is_loaded_only_for_new_due_date_and_included() -> None:
    promotion = DailyPromotion("Today only", "https://www.lidl.cz/offer")
    source = _PromotionSource(promotion)
    channel = _Channel()

    result = _workflow(channel=channel, promotion_source=source).run(_TIMESTAMP)

    assert result == DailyDigestResult(
        _DATE,
        DailyDigestStatus.SENT,
        0,
        True,
    )
    assert source.calls == 1
    assert channel.digests[0].promotion is promotion


def test_absent_promotion_sends_ordinary_digest() -> None:
    source = _PromotionSource()

    result = _workflow(promotion_source=source).run(_TIMESTAMP)

    assert result == DailyDigestResult(_DATE, DailyDigestStatus.SENT, 0, False)
    assert source.calls == 1


def test_promotion_failure_releases_reservation_and_returns_retry_outcome() -> None:
    source = _PromotionSource()
    source.error = PromotionError("offline")
    reader = _Reader()
    reservations = _Reservations()
    channel = _Channel()
    baseline = _Baselines(())

    result = _workflow(
        reader,
        reservations,
        channel,
        promotion_source=source,
        baseline_store=baseline,
    ).run(_TIMESTAMP)

    assert result == DailyDigestResult(
        _DATE,
        DailyDigestStatus.PROMOTION_UNAVAILABLE,
    )
    assert reservations.release_calls == [_DATE]
    assert reader.calls == 0
    assert channel.digests == []
    assert baseline.release_calls == []


@pytest.mark.parametrize("value", [object(), RuntimeError("bug")])
def test_unexpected_promotion_failure_releases_and_propagates(value: object) -> None:
    source = _PromotionSource(value)
    if isinstance(value, Exception):
        source.value = None
        source.error = value
    reservations = _Reservations()

    with pytest.raises((TypeError, RuntimeError)):
        _workflow(
            reservations=reservations,
            promotion_source=source,
        ).run(_TIMESTAMP)

    assert reservations.release_calls == [_DATE]


def test_timezone_conversion_handles_winter_and_summer_dates() -> None:
    summer = _workflow().run(datetime(2026, 8, 8, 6, 0, tzinfo=UTC))
    winter = _workflow().run(datetime(2026, 12, 8, 7, 0, tzinfo=UTC))

    assert summer.status is DailyDigestStatus.SENT
    assert winter.status is DailyDigestStatus.SENT
    assert winter.calendar_date == date(2026, 12, 8)


@pytest.mark.parametrize("failure_source", ["reader", "channel"])
def test_failure_releases_date_for_retry(failure_source: str) -> None:
    failure = RuntimeError("failed")
    reader = _Reader()
    channel = _Channel()
    reservations = _Reservations()
    baseline = _Baselines(())
    if failure_source == "reader":
        reader.error = failure
    else:
        channel.error = failure

    with pytest.raises(RuntimeError) as captured:
        _workflow(
            reader,
            reservations,
            channel,
            baseline_store=baseline,
        ).run(_TIMESTAMP)

    assert captured.value is failure
    assert reservations.release_calls == [_DATE]
    assert baseline.release_calls == [_DATE]


def test_baseline_failure_releases_baseline_and_date_for_retry() -> None:
    failure = RuntimeError("baseline failed")
    baseline = _Baselines(())
    baseline.error = failure
    reservations = _Reservations()

    with pytest.raises(RuntimeError) as captured:
        _workflow(
            reservations=reservations,
            baseline_store=baseline,
        ).run(_TIMESTAMP)

    assert captured.value is failure
    assert baseline.release_calls == [_DATE]
    assert reservations.release_calls == [_DATE]


def test_baseline_release_failure_propagates_from_compensation() -> None:
    baseline = _Baselines(())
    baseline.error = RuntimeError("load failed")
    baseline.release_error = RuntimeError("baseline release failed")

    with pytest.raises(RuntimeError, match="baseline release failed"):
        _workflow(baseline_store=baseline).run(_TIMESTAMP)


def test_release_failure_propagates_from_compensation() -> None:
    reader = _Reader()
    reader.error = RuntimeError("query failed")
    reservations = _Reservations()
    reservations.release_error = RuntimeError("release failed")

    with pytest.raises(RuntimeError, match="release failed"):
        _workflow(reader, reservations).run(_TIMESTAMP)


def test_reader_and_engine_contract_results_are_validated() -> None:
    reader = _Reader()
    reader.snapshots = []
    reservations = _Reservations()
    with pytest.raises(TypeError, match="return a tuple"):
        _workflow(reader, reservations).run(_TIMESTAMP)
    assert reservations.release_calls == [_DATE]

    reservations = _Reservations()
    with pytest.raises(TypeError, match="return a DailyDiscountDigest"):
        _workflow(reservations=reservations, engine=_WrongEngine()).run(_TIMESTAMP)
    assert reservations.release_calls == [_DATE]


@pytest.mark.parametrize(
    ("value", "error"),
    [
        ("now", TypeError),
        (datetime(2026, 8, 8), ValueError),
    ],
)
def test_run_rejects_invalid_timestamp(value: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        _workflow().run(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("delivery_time", "08:00", TypeError),
        ("delivery_time", time(8, tzinfo=timezone.utc), ValueError),
        ("delivery_time", time(8, 0, 1), ValueError),
        ("delivery_time", time(8, 0, 0, 1), ValueError),
        ("minimum_discount", Decimal("20"), TypeError),
    ],
)
def test_config_rejects_invalid_values(
    field: str,
    value: object,
    error: type[Exception],
) -> None:
    values: dict[str, object] = {
        "delivery_time": time(8),
        "minimum_discount": Percentage(Decimal("20")),
    }
    values[field] = value
    with pytest.raises(error):
        DailyDigestConfig(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("calendar_date", _TIMESTAMP, TypeError),
        ("calendar_date", "today", TypeError),
        ("status", "sent", TypeError),
        ("product_count", True, TypeError),
        ("product_count", Decimal("1"), TypeError),
        ("product_count", -1, ValueError),
        ("promotion_included", 1, TypeError),
    ],
)
def test_result_rejects_invalid_values(
    field: str,
    value: object,
    error: type[Exception],
) -> None:
    values: dict[str, object] = {
        "calendar_date": _DATE,
        "status": DailyDigestStatus.SENT,
        "product_count": 0,
        "promotion_included": False,
    }
    values[field] = value
    with pytest.raises(error):
        DailyDigestResult(**values)  # type: ignore[arg-type]


def test_non_delivery_result_rejects_nonzero_count() -> None:
    with pytest.raises(ValueError, match="non-delivery"):
        DailyDigestResult(_DATE, DailyDigestStatus.NOT_DUE, 1)
    with pytest.raises(ValueError, match="cannot include"):
        DailyDigestResult(
            _DATE,
            DailyDigestStatus.PROMOTION_UNAVAILABLE,
            promotion_included=True,
        )


@pytest.mark.parametrize(
    ("position", "replacement", "match"),
    [
        (0, object(), "snapshot_reader"),
        (1, object(), "reservation_store"),
        (1, type("OnlyReserve", (), {"reserve": lambda *args: True})(), "release"),
        (2, object(), "digest_engine"),
        (3, object(), "digest_channel"),
        (4, object(), "config"),
        (5, object(), "timezone"),
    ],
)
def test_constructor_rejects_invalid_dependencies(
    position: int,
    replacement: object,
    match: str,
) -> None:
    arguments: list[object] = [
        _Reader(),
        _Reservations(),
        DailyDiscountDigestEngine(),
        _Channel(),
        DailyDigestConfig(time(8), Percentage(Decimal("20"))),
        _PRAGUE,
    ]
    arguments[position] = replacement
    with pytest.raises(TypeError, match=match):
        DailyDigestWorkflow(*arguments)  # type: ignore[arg-type]


def test_constructor_rejects_invalid_promotion_source() -> None:
    with pytest.raises(TypeError, match="promotion_source"):
        _workflow(promotion_source=cast(_PromotionSource, object()))


@pytest.mark.parametrize("missing", ["previous_product_ids", "stage", "release"])
def test_constructor_rejects_invalid_baseline_store(missing: str) -> None:
    methods = {
        "previous_product_ids": lambda *args: None,
        "stage": lambda *args: None,
        "release": lambda *args: None,
    }
    del methods[missing]
    invalid = type("InvalidBaseline", (), methods)()

    with pytest.raises(TypeError, match="baseline_store"):
        _workflow(baseline_store=cast(_Baselines, invalid))


def test_public_api_is_explicit_documented_typed_and_immutable() -> None:
    assert digest_api.__all__ == [
        "DailyDigestConfig",
        "DailyDigestResult",
        "DailyDigestStatus",
        "DailyDigestWorkflow",
    ]
    assert tuple(DailyDigestStatus) == (
        DailyDigestStatus.NOT_DUE,
        DailyDigestStatus.ALREADY_SENT,
        DailyDigestStatus.PROMOTION_UNAVAILABLE,
        DailyDigestStatus.SENT,
    )
    config = DailyDigestConfig(time(8), Percentage(Decimal("20")))
    with pytest.raises(AttributeError):
        config.delivery_time = time(9)  # type: ignore[misc]
    for public_object in (
        DailyDigestConfig,
        DailyDigestResult,
        DailyDigestStatus,
        DailyDigestWorkflow,
    ):
        assert inspect.getdoc(public_object)
    assert inspect.signature(DailyDigestWorkflow.run).return_annotation is (
        DailyDigestResult
    )
