"""Immutable result of a completed synchronization workflow."""

from dataclasses import dataclass

from core.domain import Notification
from core.provider import FetchResult, ProviderError
from core.rules import EvaluationResult
from core.state import StateSnapshot


@dataclass(frozen=True, slots=True)
class SynchronizationResult:
    """Report completed synchronization operations in processing order."""

    fetch_results: tuple[FetchResult, ...]
    evaluations: tuple[EvaluationResult, ...]
    notifications: tuple[Notification, ...]
    snapshots: tuple[StateSnapshot, ...]
    provider_errors: tuple[ProviderError, ...]
    suppressed_notification_count: int = 0

    def __post_init__(self) -> None:
        """Validate result collection types."""
        _validate_tuple(self.fetch_results, FetchResult, "fetch_results")
        _validate_tuple(self.evaluations, EvaluationResult, "evaluations")
        _validate_tuple(self.notifications, Notification, "notifications")
        _validate_tuple(self.snapshots, StateSnapshot, "snapshots")
        _validate_tuple(self.provider_errors, ProviderError, "provider_errors")
        if isinstance(self.suppressed_notification_count, bool) or not isinstance(
            self.suppressed_notification_count,
            int,
        ):
            raise TypeError("suppressed_notification_count must be an int")
        if self.suppressed_notification_count < 0:
            raise ValueError("suppressed_notification_count cannot be negative")


def _validate_tuple(
    value: object,
    item_type: type[object],
    field_name: str,
) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(item, item_type) for item in value
    ):
        raise TypeError(f"{field_name} must be a tuple of {item_type.__name__}")
