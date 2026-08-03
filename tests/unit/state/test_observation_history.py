"""Tests for the read-only observation-history Core contract."""

import inspect

import core.state as state_api
from core.domain import ProductId
from core.state import ObservationHistory, StateSnapshot, StateStore, StateStoreError


class _History:
    def history(
        self,
        product_id: ProductId,
        limit: int | None = None,
    ) -> tuple[StateSnapshot, ...]:
        return ()


def _as_history(history: ObservationHistory) -> ObservationHistory:
    return history


def test_observation_history_is_a_structural_protocol() -> None:
    history = _History()

    assert _as_history(history) is history


def test_core_state_public_api_is_explicit() -> None:
    assert state_api.__all__ == [
        "ObservationHistory",
        "StateSnapshot",
        "StateStore",
        "StateStoreError",
    ]
    assert state_api.ObservationHistory is ObservationHistory
    assert state_api.StateSnapshot is StateSnapshot
    assert state_api.StateStore is StateStore
    assert state_api.StateStoreError is StateStoreError


def test_observation_history_is_documented_and_typed() -> None:
    assert inspect.getdoc(ObservationHistory)
    assert inspect.getdoc(ObservationHistory.history)
    assert inspect.signature(ObservationHistory.history).return_annotation == (
        tuple[StateSnapshot, ...]
    )