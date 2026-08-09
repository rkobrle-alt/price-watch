"""Tests for immutable observation statistics and their read contract."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import cast

import pytest

from core.state import ObservationStatistics, ObservationStatisticsReader

_FIRST = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
_LAST = datetime(2026, 8, 2, 8, 0, tzinfo=UTC)


class _Reader:
    def observation_statistics(self) -> ObservationStatistics:
        return ObservationStatistics(2, 1, _FIRST, _LAST, 4096)


def test_statistics_are_immutable_slotted_and_structurally_readable() -> None:
    statistics = _Reader().observation_statistics()
    reader: ObservationStatisticsReader = _Reader()

    assert reader.observation_statistics() == statistics
    assert not hasattr(statistics, "__dict__")
    with pytest.raises(FrozenInstanceError):
        statistics.observation_count = 3  # type: ignore[misc]


def test_empty_statistics_require_no_products_or_timestamps() -> None:
    assert ObservationStatistics(0, 0, None, None, 8192) == (
        ObservationStatistics(0, 0, None, None, 8192)
    )


@pytest.mark.parametrize(
    ("changes", "exception_type", "message"),
    [
        ({"observation_count": True}, TypeError, "observation_count"),
        ({"observation_count": -1}, ValueError, "observation_count"),
        ({"observed_product_count": "1"}, TypeError, "observed_product_count"),
        ({"storage_size_bytes": -1}, ValueError, "storage_size_bytes"),
        ({"observed_product_count": 3}, ValueError, "cannot exceed"),
        (
            {"first_observation_at": "now"},
            TypeError,
            "first_observation_at",
        ),
        (
            {"last_observation_at": datetime(2026, 8, 2)},
            ValueError,
            "timezone-aware",
        ),
        (
            {"observation_count": 0, "observed_product_count": 1,
             "first_observation_at": None, "last_observation_at": None},
            ValueError,
            "cannot exceed",
        ),
        (
            {"observation_count": 0, "observed_product_count": 0,
             "last_observation_at": None},
            ValueError,
            "cannot have timestamps",
        ),
        ({"last_observation_at": None}, ValueError, "both timestamps"),
    ],
)
def test_statistics_reject_invalid_values(
    changes: dict[str, object],
    exception_type: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "observation_count": 2,
        "observed_product_count": 1,
        "first_observation_at": _FIRST,
        "last_observation_at": _LAST,
        "storage_size_bytes": 4096,
    }
    values.update(changes)

    with pytest.raises(exception_type, match=message):
        ObservationStatistics(**cast(dict, values))
