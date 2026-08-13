"""Calendar-based daily digest application orchestration."""

from datetime import datetime, tzinfo
from typing import cast

from applications.daily_digest.configuration import DailyDigestConfig
from applications.daily_digest.result import DailyDigestResult, DailyDigestStatus
from core.notifications import (
    DailyDigestReservationStore,
    DailyDiscountDigest,
    DailyDiscountDigestChannel,
    DailyDiscountDigestEngine,
)
from core.promotions import DailyPromotion, DailyPromotionSource, PromotionError
from core.state import LatestSnapshotReader


class DailyDigestWorkflow:
    """Deliver at most one configured digest per local calendar date."""

    def __init__(
        self,
        snapshot_reader: LatestSnapshotReader,
        reservation_store: DailyDigestReservationStore,
        digest_engine: DailyDiscountDigestEngine,
        digest_channel: DailyDiscountDigestChannel,
        config: DailyDigestConfig,
        timezone: tzinfo,
        *,
        promotion_source: DailyPromotionSource | None = None,
    ) -> None:
        """Validate and retain explicit workflow collaborators."""
        _require_method(snapshot_reader, "latest_snapshots", "snapshot_reader")
        _require_method(reservation_store, "reserve", "reservation_store")
        _require_method(reservation_store, "release", "reservation_store")
        if not isinstance(digest_engine, DailyDiscountDigestEngine):
            raise TypeError("digest_engine must be a DailyDiscountDigestEngine")
        _require_method(digest_channel, "send", "digest_channel")
        if not isinstance(config, DailyDigestConfig):
            raise TypeError("config must be a DailyDigestConfig")
        if not isinstance(timezone, tzinfo):
            raise TypeError("timezone must be a tzinfo")
        if promotion_source is not None:
            _require_method(promotion_source, "current", "promotion_source")
        self._snapshot_reader = cast(LatestSnapshotReader, snapshot_reader)
        self._reservation_store = cast(
            DailyDigestReservationStore,
            reservation_store,
        )
        self._digest_engine = digest_engine
        self._digest_channel = cast(DailyDiscountDigestChannel, digest_channel)
        self._config = config
        self._timezone = timezone
        self._promotion_source = cast(
            DailyPromotionSource | None,
            promotion_source,
        )

    def run(self, timestamp: datetime) -> DailyDigestResult:
        """Evaluate local eligibility and deliver one restart-safe digest."""
        _validate_timestamp(timestamp)
        local_timestamp = timestamp.astimezone(self._timezone)
        calendar_date = local_timestamp.date()
        local_time = local_timestamp.timetz().replace(tzinfo=None)
        if local_time < self._config.delivery_time:
            return DailyDigestResult(calendar_date, DailyDigestStatus.NOT_DUE)
        if not self._reservation_store.reserve(calendar_date, timestamp):
            return DailyDigestResult(calendar_date, DailyDigestStatus.ALREADY_SENT)
        try:
            promotion = self._current_promotion()
            snapshots = self._snapshot_reader.latest_snapshots()
            if not isinstance(snapshots, tuple):
                raise TypeError("snapshot_reader must return a tuple")
            digest = self._digest_engine.generate(
                snapshots,
                self._config.minimum_discount,
                calendar_date,
                timestamp,
                promotion,
            )
            if not isinstance(digest, DailyDiscountDigest):
                raise TypeError("digest_engine must return a DailyDiscountDigest")
            self._digest_channel.send(digest)
        except PromotionError:
            self._reservation_store.release(calendar_date)
            return DailyDigestResult(
                calendar_date,
                DailyDigestStatus.PROMOTION_UNAVAILABLE,
            )
        except Exception:
            self._reservation_store.release(calendar_date)
            raise
        return DailyDigestResult(
            calendar_date,
            DailyDigestStatus.SENT,
            len(digest.products),
            digest.promotion is not None,
        )

    def _current_promotion(self) -> DailyPromotion | None:
        if self._promotion_source is None:
            return None
        promotion = self._promotion_source.current()
        if promotion is not None and not isinstance(promotion, DailyPromotion):
            raise TypeError(
                "promotion_source must return a DailyPromotion or None"
            )
        return promotion


def _require_method(value: object, method: str, name: str) -> None:
    if not callable(getattr(value, method, None)):
        raise TypeError(f"{name} must expose a callable {method} method")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
