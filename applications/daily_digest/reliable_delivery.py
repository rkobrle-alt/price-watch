"""Serialized recoverable digest preparation and conservative external handoff."""

from collections.abc import Callable
from datetime import date, datetime, tzinfo

from applications.daily_digest.configuration import DailyDigestConfig
from applications.daily_digest.result import DailyDigestResult, DailyDigestStatus as Status
from core.notifications import (
    DailyDigestBaselineStore, DailyDiscountDigest, DailyDiscountDigestChannel,
    DigestDeliveryPhase as Phase, DigestDeliveryStore, DigestPromotionPolicy,
    NotificationDeliveryRejectedError,
)
from core.promotions import DailyPromotion, PromotionError
from core.provider import ProviderError


class _ReliableDigestDelivery:
    """Coordinate one live App writer; never take over another active worker."""

    def __init__(
        self, store: DigestDeliveryStore,
        prepare: Callable[[datetime, date, DailyPromotion | None], tuple[DailyDiscountDigest, tuple[ProviderError, ...]]],
        promotion: Callable[[], DailyPromotion | None], channel: DailyDiscountDigestChannel,
        baseline: DailyDigestBaselineStore | None, config: DailyDigestConfig, timezone: tzinfo,
    ) -> None:
        self._store, self._prepare, self._promotion = store, prepare, promotion
        self._channel, self._baseline = channel, baseline
        self._config, self._timezone = config, timezone
        self._recovered = False

    def run(self, timestamp: datetime) -> DailyDigestResult:
        """Recover pre-dispatch work, bound banner delays and retain uncertainty."""
        if not self._recovered:
            self._store.recover(timestamp)
            self._recovered = True
        local = timestamp.astimezone(self._timezone)
        calendar_date = local.date()
        scheduled = datetime.combine(calendar_date, self._config.delivery_time, self._timezone)
        if local < scheduled:
            return DailyDigestResult(calendar_date, Status.NOT_DUE)
        phase = self._store.claim(calendar_date, timestamp)
        if phase in {Phase.ACCEPTED, Phase.LEGACY_RESERVED}:
            return DailyDigestResult(calendar_date, Status.ALREADY_SENT)
        if phase in {Phase.SENDING, Phase.UNCERTAIN}:
            return DailyDigestResult(calendar_date, Status.DELIVERY_UNCERTAIN)
        if phase is Phase.PREPARING:
            return self._prepare_and_dispatch(calendar_date, timestamp, scheduled)
        raise ValueError("claim must return retained evidence or preparing")

    def _prepare_and_dispatch(self, calendar_date: date, timestamp: datetime, scheduled: datetime) -> DailyDigestResult:
        missing = False
        try:
            try:
                promotion = self._promotion()
            except PromotionError:
                if not DigestPromotionPolicy().can_fallback(timestamp, scheduled):
                    self._store.transition(calendar_date, Phase.PREPARING, Phase.READY, timestamp)
                    return DailyDigestResult(calendar_date, Status.PROMOTION_UNAVAILABLE)
                promotion, missing = None, True
            digest, errors = self._prepare(timestamp, calendar_date, promotion)
            if missing:
                digest = DigestPromotionPolicy().fallback_digest(digest)
            if self._baseline is not None:
                self._baseline.stage(calendar_date, tuple(p.id for p in digest.products))
        except Exception:
            self._store.transition(calendar_date, Phase.PREPARING, Phase.READY, timestamp)
            raise
        metadata = dict(product_count=len(digest.products), promotion_included=digest.promotion is not None, promotion_missing=missing)
        # Failure to persist this marker must never reach the external channel.
        self._store.transition(calendar_date, Phase.PREPARING, Phase.SENDING, timestamp, **metadata)
        try:
            self._channel.send(digest)
        except NotificationDeliveryRejectedError:
            self._store.transition(calendar_date, Phase.SENDING, Phase.READY, timestamp)
            return DailyDigestResult(calendar_date, Status.DELIVERY_RETRY)
        except Exception:
            self._store.transition(calendar_date, Phase.SENDING, Phase.UNCERTAIN, timestamp, **metadata)
            return DailyDigestResult(calendar_date, Status.DELIVERY_UNCERTAIN)
        # A failure here retains sending; startup recovery marks it uncertain.
        self._store.transition(calendar_date, Phase.SENDING, Phase.ACCEPTED, timestamp, **metadata)
        return DailyDigestResult(calendar_date, Status.SENT, len(digest.products), digest.promotion is not None, errors, missing)
