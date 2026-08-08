"""Tests for immutable synchronization results."""

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from applications.synchronization import SynchronizationResult
from core.domain import Notification
from core.provider import FetchResult, ProviderError
from core.rules import EvaluationResult
from core.state import StateSnapshot
from tests.unit.applications.helpers import (
    NOTIFICATION_IDS,
    TIMESTAMP,
    create_fetch_result,
    create_product,
)


def _valid_result() -> SynchronizationResult:
    product = create_product()
    evaluation = EvaluationResult(True, "matched", TIMESTAMP)
    notification = Notification(
        NOTIFICATION_IDS[0],
        product.id,
        evaluation.reason,
        TIMESTAMP,
    )
    snapshot = StateSnapshot(product, TIMESTAMP)
    return SynchronizationResult(
        fetch_results=(create_fetch_result((product,)),),
        evaluations=(evaluation,),
        notifications=(notification,),
        snapshots=(snapshot,),
        provider_errors=(ProviderError("provider failed"),),
    )


def test_result_retains_typed_values_and_is_immutable() -> None:
    result = _valid_result()

    assert result.fetch_results[0].products == (result.snapshots[0].product,)
    assert result.evaluations[0].matched
    assert result.notifications[0].message == "matched"
    assert str(result.provider_errors[0]) == "provider failed"
    assert result.suppressed_notification_count == 0
    with pytest.raises(FrozenInstanceError):
        result.snapshots = ()


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("fetch_results", cast(tuple[FetchResult, ...], [])),
        ("fetch_results", (object(),)),
        ("evaluations", cast(tuple[EvaluationResult, ...], [])),
        ("evaluations", (object(),)),
        ("notifications", cast(tuple[Notification, ...], [])),
        ("notifications", (object(),)),
        ("snapshots", cast(tuple[StateSnapshot, ...], [])),
        ("snapshots", (object(),)),
        ("provider_errors", cast(tuple[ProviderError, ...], [])),
        ("provider_errors", (object(),)),
    ],
)
def test_result_rejects_invalid_collections(
    field_name: str,
    invalid_value: object,
) -> None:
    values: dict[str, object] = {
        "fetch_results": (),
        "evaluations": (),
        "notifications": (),
        "snapshots": (),
        "provider_errors": (),
    }
    values[field_name] = invalid_value

    with pytest.raises(TypeError, match=field_name):
        SynchronizationResult(**values)


@pytest.mark.parametrize(
    ("value", "exception"),
    [(True, TypeError), (1.5, TypeError), (-1, ValueError)],
)
def test_result_rejects_invalid_suppressed_notification_count(
    value: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception, match="suppressed_notification_count"):
        SynchronizationResult((), (), (), (), (), value)  # type: ignore[arg-type]
