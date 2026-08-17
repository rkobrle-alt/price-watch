"""Persistence contract for daily digest product membership baselines."""

from datetime import date
from typing import Protocol

from core.domain import ProductId


class DailyDigestBaselineStore(Protocol):
    """Persist and retrieve successful daily digest product memberships."""

    def previous_product_ids(
        self,
        calendar_date: date,
    ) -> tuple[ProductId, ...] | None:
        """Return the latest membership strictly before ``calendar_date``."""
        ...

    def stage(
        self,
        calendar_date: date,
        product_ids: tuple[ProductId, ...],
    ) -> None:
        """Stage the membership associated with one digest date."""
        ...

    def release(self, calendar_date: date) -> None:
        """Idempotently remove a staged membership after delivery failure."""
        ...
