"""Frequency-independent daily price context from streamed observations."""

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta, tzinfo
from decimal import Decimal
from itertools import chain
from statistics import median

from core.domain import Money
from core.pricing.model import PriceHistoryAssessment, PriceValueRating as Rating, _validate_timestamp
from core.state import StateSnapshot


class PriceHistoryEngine:
    """Assess recorded prices without I/O or invented coverage."""

    def __init__(self, timezone: tzinfo) -> None:
        """Use an injected timezone for deterministic calendar-day windows."""
        if not isinstance(timezone, tzinfo):
            raise TypeError("timezone must be tzinfo")
        self._timezone = timezone

    def assess(
        self, current: StateSnapshot, history: Iterable[StateSnapshot], timestamp: datetime,
    ) -> PriceHistoryAssessment:
        """Stream history, retaining one closing amount per observed local day."""
        if not isinstance(current, StateSnapshot):
            raise TypeError("current must be a StateSnapshot")
        if not isinstance(history, Iterable):
            raise TypeError("history must be iterable")
        _validate_timestamp(timestamp)
        asof = timestamp.astimezone(UTC)
        today = timestamp.astimezone(self._timezone).date()
        start_30, start_90 = today - timedelta(days=29), today - timedelta(days=89)
        closes: dict[date, tuple[datetime, Decimal]] = {}
        minimum_30 = minimum_90 = first = None
        for snapshot in chain(history, (current,)):
            if not isinstance(snapshot, StateSnapshot):
                raise TypeError("history must contain StateSnapshot values")
            product = snapshot.product
            if product.id != current.product.id:
                raise ValueError("history must belong to the current product")
            instant = snapshot.timestamp.astimezone(UTC)
            if instant > asof or product.currency is not current.product.currency or not product.availability:
                continue
            day = snapshot.timestamp.astimezone(self._timezone).date()
            amount = product.current_price.amount
            if first is None or instant < first.astimezone(UTC):
                first = snapshot.timestamp
            previous = closes.get(day)
            if previous is None or instant >= previous[0]:
                closes[day] = (instant, amount)
            if day >= start_30:
                minimum_30 = amount if minimum_30 is None else min(minimum_30, amount)
            if day >= start_90:
                minimum_90 = amount if minimum_90 is None else min(minimum_90, amount)
        prior = [value[1] for day, value in closes.items() if start_90 <= day < today]
        usual = Money(median(prior), current.product.currency) if prior else None
        current_amount = current.product.current_price.amount
        saving = None if usual is None or usual.amount == 0 else (usual.amount - current_amount) * Decimal(100) / usual.amount
        last_drop = None
        previous_amount = None
        for day in sorted(closes):
            amount = closes[day][1]
            if previous_amount is not None and amount < previous_amount:
                last_drop = day
            previous_amount = amount
        fresh = current.product.availability and timedelta(0) <= asof - current.timestamp.astimezone(UTC) <= timedelta(hours=1)
        rating = _rating(fresh, len(prior), current_amount, usual, saving, minimum_90)
        return PriceHistoryAssessment(
            current.product.id, current.product.current_price, current.timestamp, timestamp, first,
            0 if first is None else (today - first.astimezone(self._timezone).date()).days + 1,
            sum(day >= start_30 for day in closes), sum(day >= start_90 for day in closes), len(prior),
            None if minimum_30 is None else Money(minimum_30, current.product.currency),
            None if minimum_90 is None else Money(minimum_90, current.product.currency),
            usual, saving, last_drop, rating,
        )


def _rating(
    fresh: bool, prior_days: int, amount: Decimal, usual: Money | None,
    saving: Decimal | None, minimum_90: Decimal | None,
) -> Rating:
    if not fresh:
        return Rating.UNVERIFIED
    if prior_days < 7:
        return Rating.INSUFFICIENT_HISTORY
    if amount == usual.amount:
        return Rating.NORMAL
    if amount > usual.amount:
        return Rating.ABOVE_USUAL
    if saving >= Decimal(10):
        return Rating.EXCELLENT if amount == minimum_90 else Rating.GOOD
    return Rating.LOWER
