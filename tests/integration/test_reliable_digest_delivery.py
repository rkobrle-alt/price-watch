"""Crash boundaries and banner deadlines with a real restartable SQLite ledger."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from applications.daily_digest import DailyDigestWorkflow, DailyDigestConfig, DailyDigestStatus as Status
from core.domain import Percentage
from core.notifications import DailyDiscountDigestEngine, DigestDeliveryPhase as Phase, DailyDigestReservationError, NotificationDeliveryRejectedError
from core.promotions import PromotionError, DailyPromotion
from core.state import StateSnapshot
from infrastructure.persistence.sqlite import SqliteDigestDeliveryStore, SqliteDailyDigestBaselineStore, SqliteDailyDigestReservationStore, SqliteStateStore
from tests.unit.daily_digest.test_workflow import _Reader, _Channel, _PromotionSource
from tests.unit.notifications.test_daily_digest import _product

NOW = datetime(2026, 11, 19, 7, tzinfo=UTC)


class Crash(BaseException):
    """Simulate process death outside compensatable exception handlers."""


def build(path: Path, channel=None, reader=None, source=None, store=None, baseline=True):
    return DailyDigestWorkflow(
        reader or _Reader((StateSnapshot(_product(1, "Tool", "20"), NOW),)),
        SqliteDailyDigestReservationStore(path), DailyDiscountDigestEngine(), channel or _Channel(),
        DailyDigestConfig(time(8), Percentage(Decimal("20"))), ZoneInfo("Europe/Prague"),
        baseline_store=SqliteDailyDigestBaselineStore(path) if baseline else None,
        promotion_source=source, delivery_store=store or SqliteDigestDeliveryStore(path),
    )


def test_banner_retries_until_deadline_then_sends_once_with_warning(tmp_path: Path) -> None:
    path, channel, source = tmp_path / "db", _Channel(), _PromotionSource()
    source.error = PromotionError("banner unavailable")
    workflow = build(path, channel, source=source)
    assert workflow.run(NOW - timedelta(seconds=1)).status is Status.NOT_DUE
    assert workflow.run(NOW).status is Status.PROMOTION_UNAVAILABLE
    assert workflow.run(NOW + timedelta(minutes=30, seconds=-1)).status is Status.PROMOTION_UNAVAILABLE
    assert channel.digests == []
    result = workflow.run(NOW + timedelta(minutes=30))
    assert result.status is Status.SENT and result.promotion_missing and not result.promotion_included
    assert "Dnešní akci Lidlu se nepodařilo ověřit" in channel.digests[0].message
    record = SqliteDigestDeliveryStore(path).latest()
    assert record.phase is Phase.ACCEPTED and record.promotion_missing
    source.error = None
    assert build(path, channel, source=source).run(NOW + timedelta(hours=1)).status is Status.ALREADY_SENT
    assert len(channel.digests) == 1


def test_late_start_falls_back_without_another_wait_and_absent_banner_is_normal(tmp_path: Path) -> None:
    source = _PromotionSource()
    source.error = PromotionError("offline")
    assert build(tmp_path / "late", source=source, baseline=False).run(NOW + timedelta(hours=10)).promotion_missing
    source.error = None
    source.promotion = None
    assert not build(tmp_path / "absent", source=source).run(NOW).promotion_missing


def test_crash_during_preparation_is_recovered_and_history_is_preserved(tmp_path: Path) -> None:
    path, channel = tmp_path / "db", _Channel()
    reader = _Reader()
    reader.error = Crash()
    with pytest.raises(Crash):
        build(path, channel, reader).run(NOW)
    assert SqliteDigestDeliveryStore(path).latest().phase is Phase.PREPARING
    reader.error = None
    assert build(path, channel, reader).run(NOW + timedelta(minutes=5)).status is Status.SENT
    assert len(channel.digests) == 1


def test_crash_during_handoff_never_automatically_resends_or_advances_baseline(tmp_path: Path) -> None:
    path = tmp_path / "db"
    class Interrupted(_Channel):
        def send(self, digest):
            self.digests.append(digest)
            raise Crash()
    channel = Interrupted()
    with pytest.raises(Crash):
        build(path, channel).run(NOW)
    assert SqliteDigestDeliveryStore(path).latest().phase is Phase.SENDING
    assert SqliteDailyDigestBaselineStore(path).previous_product_ids(NOW.date() + timedelta(days=1)) is None
    assert build(path, channel).run(NOW + timedelta(minutes=5)).status is Status.DELIVERY_UNCERTAIN
    assert len(channel.digests) == 1
    assert SqliteDigestDeliveryStore(path).latest().phase is Phase.UNCERTAIN


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), RuntimeError("unknown channel failure")])
def test_ambiguous_channel_failure_remains_uncertain(tmp_path: Path, failure: Exception) -> None:
    path, channel = tmp_path / "db", _Channel()
    channel.error = failure
    workflow = build(path, channel)
    assert workflow.run(NOW).status is Status.DELIVERY_UNCERTAIN
    channel.error = None
    assert workflow.run(NOW + timedelta(minutes=5)).status is Status.DELIVERY_UNCERTAIN
    assert channel.digests == []


def test_known_rejection_retries_on_next_cycle(tmp_path: Path) -> None:
    path, channel = tmp_path / "db", _Channel()
    channel.error = NotificationDeliveryRejectedError("rejected before execution")
    workflow = build(path, channel)
    assert workflow.run(NOW).status is Status.DELIVERY_RETRY
    assert SqliteDigestDeliveryStore(path).latest().phase is Phase.READY
    channel.error = None
    assert workflow.run(NOW + timedelta(minutes=5)).status is Status.SENT
    assert len(channel.digests) == 1


@pytest.mark.parametrize("phase", [Phase.SENDING, Phase.ACCEPTED])
def test_persistence_failure_never_releases_handoff_evidence(tmp_path: Path, monkeypatch, phase: Phase) -> None:
    path, channel = tmp_path / "db", _Channel()
    store = SqliteDigestDeliveryStore(path)
    original = store.transition
    def fail(calendar_date, expected, target, timestamp, **metadata):
        if target is phase:
            raise DailyDigestReservationError("disk failed")
        return original(calendar_date, expected, target, timestamp, **metadata)
    monkeypatch.setattr(store, "transition", fail)
    with pytest.raises(DailyDigestReservationError):
        build(path, channel, store=store).run(NOW)
    if phase is Phase.SENDING:
        assert channel.digests == []
        assert build(path, channel).run(NOW + timedelta(minutes=5)).status is Status.SENT
    else:
        assert len(channel.digests) == 1
        assert build(path, channel).run(NOW + timedelta(minutes=5)).status is Status.DELIVERY_UNCERTAIN
        assert len(channel.digests) == 1


def test_preparation_error_releases_date_and_candidate_baseline(tmp_path: Path) -> None:
    path, reader = tmp_path / "db", _Reader()
    reader.error = RuntimeError("prepare failed")
    workflow = build(path, reader=reader)
    with pytest.raises(RuntimeError):
        workflow.run(NOW)
    assert SqliteDigestDeliveryStore(path).latest().phase is Phase.READY
    reader.error = None
    assert workflow.run(NOW + timedelta(minutes=5)).status is Status.SENT


def test_legacy_reservation_is_never_replayed(tmp_path: Path) -> None:
    path, channel = tmp_path / "db", _Channel()
    SqliteDailyDigestReservationStore(path).reserve(NOW.date(), NOW)
    assert build(path, channel).run(NOW).status is Status.ALREADY_SENT
    assert SqliteDigestDeliveryStore(path).latest().phase is Phase.LEGACY_RESERVED
    assert channel.digests == []
