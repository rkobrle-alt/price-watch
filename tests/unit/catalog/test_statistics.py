"""Tests for immutable provider-neutral catalog statistics."""

from datetime import datetime
from typing import cast

import pytest

from core.catalog import CatalogStatistics
from tests.unit.homeassistant_app.helpers import TIMESTAMP


def test_statistics_are_immutable_and_accept_unknown_times() -> None:
    statistics = CatalogStatistics(0, None, None)

    assert statistics.reference_count == 0
    with pytest.raises(AttributeError):
        statistics.reference_count = 1


@pytest.mark.parametrize(
    ("arguments", "exception_type", "message"),
    [
        ((True, None, None), TypeError, "reference_count"),
        (("1", None, None), TypeError, "reference_count"),
        ((-1, None, None), ValueError, "reference_count"),
        ((0, "now", None), TypeError, "last_discovered_at"),
        (
            (0, datetime(2026, 8, 8, 10, 0), None),
            ValueError,
            "last_discovered_at",
        ),
        ((0, TIMESTAMP, "now"), TypeError, "last_refresh_attempt_at"),
        (
            (0, TIMESTAMP, datetime(2026, 8, 8, 10, 0)),
            ValueError,
            "last_refresh_attempt_at",
        ),
    ],
)
def test_statistics_reject_invalid_values(
    arguments: tuple[object, object, object],
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        CatalogStatistics(*cast(tuple[int, datetime | None, datetime | None], arguments))
