"""Application orchestration for complete product synchronization cycles."""

from collections.abc import Callable
from datetime import datetime
from typing import cast
from uuid import UUID

from applications.synchronization._alerts import _AlertCoordinator
from applications.synchronization.result import SynchronizationResult
from core.domain import Notification, ProviderId, Rule
from core.notifications import (
    NotificationChannel,
    NotificationEngine,
    NotificationReservationStore,
    PriceDropReservationPolicy,
)
from core.provider import FetchResult, Provider, ProviderError
from core.rules import EvaluationResult, PriceReferencePolicy, RuleEngine
from core.state import ObservationHistory, StateSnapshot, StateStore


class SynchronizationWorkflow:
    """Coordinate providers, Core services and injected side-effect boundaries."""

    def __init__(
        self,
        providers: tuple[Provider, ...],
        state_store: StateStore,
        rule_engine: RuleEngine,
        notification_engine: NotificationEngine,
        notification_channel: NotificationChannel,
        notification_id_factory: Callable[[], UUID],
        *,
        observation_history: ObservationHistory | None = None,
        price_reference_policy: PriceReferencePolicy | None = None,
        notification_reservation_store: NotificationReservationStore | None = None,
        price_drop_reservation_policy: PriceDropReservationPolicy | None = None,
    ) -> None:
        """Configure a reusable workflow without invoking its dependencies."""
        self._providers = _validate_providers(providers)
        _validate_dependency(state_store, ("load", "save"), "state_store")
        _validate_dependency(rule_engine, ("evaluate",), "rule_engine")
        _validate_dependency(
            notification_engine,
            ("generate",),
            "notification_engine",
        )
        _validate_dependency(
            notification_channel,
            ("send",),
            "notification_channel",
        )
        if not callable(notification_id_factory):
            raise TypeError("notification_id_factory must be callable")
        self._state_store = cast(StateStore, state_store)
        self._rule_engine = cast(RuleEngine, rule_engine)
        self._alerts = _AlertCoordinator(
            cast(NotificationEngine, notification_engine),
            cast(NotificationChannel, notification_channel),
            notification_id_factory,
            observation_history,
            price_reference_policy,
            notification_reservation_store,
            price_drop_reservation_policy,
        )

    def run(
        self,
        rules: tuple[Rule, ...],
        timestamp: datetime,
    ) -> SynchronizationResult:
        """Run one synchronization cycle using explicit rules and timestamp."""
        _validate_run_arguments(rules, timestamp)
        fetch_results: list[FetchResult] = []
        evaluations: list[EvaluationResult] = []
        notifications: list[Notification] = []
        snapshots: list[StateSnapshot] = []
        provider_errors: list[ProviderError] = []
        suppressed_notification_count = 0

        for provider in self._providers:
            try:
                fetch_result = provider.fetch()
            except ProviderError as error:
                provider_errors.append(error)
                continue
            if not isinstance(fetch_result, FetchResult):
                raise TypeError("provider fetch must return a FetchResult")

            fetch_results.append(fetch_result)
            provider_errors.extend(fetch_result.errors)
            for product in fetch_result.products:
                product = self._alerts.enrich(product)
                previous_snapshot = self._state_store.load(product.id)
                previous = (
                    None
                    if previous_snapshot is None
                    else previous_snapshot.product
                )
                for rule in rules:
                    evaluation = self._rule_engine.evaluate(
                        rule,
                        previous,
                        product,
                        timestamp,
                    )
                    evaluations.append(evaluation)
                    notification, suppressed = self._alerts.notify(
                        rule,
                        product,
                        evaluation,
                        timestamp,
                    )
                    if suppressed:
                        suppressed_notification_count += 1
                        continue
                    if notification is not None:
                        notifications.append(notification)

                snapshot = StateSnapshot(product=product, timestamp=timestamp)
                self._state_store.save(snapshot)
                snapshots.append(snapshot)

        return SynchronizationResult(
            fetch_results=tuple(fetch_results),
            evaluations=tuple(evaluations),
            notifications=tuple(notifications),
            snapshots=tuple(snapshots),
            provider_errors=tuple(provider_errors),
            suppressed_notification_count=suppressed_notification_count,
        )

def _validate_providers(providers: object) -> tuple[Provider, ...]:
    if not isinstance(providers, tuple):
        raise TypeError("providers must be a tuple of Provider implementations")
    if not providers:
        raise ValueError("providers cannot be empty")
    for provider in providers:
        _validate_provider(provider)
    return cast(tuple[Provider, ...], providers)


def _validate_provider(provider: object) -> None:
    try:
        provider_id = getattr(provider, "id")
        display_name = getattr(provider, "display_name")
        version = getattr(provider, "version")
        fetch = getattr(provider, "fetch")
    except AttributeError as error:
        raise TypeError("provider does not implement the Provider contract") from error

    if not isinstance(provider_id, ProviderId):
        raise TypeError("provider id must be a ProviderId")
    _validate_provider_text(display_name, "display_name")
    _validate_provider_text(version, "version")
    if not callable(fetch):
        raise TypeError("provider fetch must be callable")


def _validate_provider_text(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"provider {field_name} must be a string")
    if not value.strip():
        raise ValueError(f"provider {field_name} cannot be blank")


def _validate_dependency(
    dependency: object,
    methods: tuple[str, ...],
    dependency_name: str,
) -> None:
    for method in methods:
        if not callable(getattr(dependency, method, None)):
            raise TypeError(
                f"{dependency_name} must expose a callable {method} method"
            )


def _validate_run_arguments(rules: object, timestamp: object) -> None:
    if not isinstance(rules, tuple) or not all(
        isinstance(rule, Rule) for rule in rules
    ):
        raise TypeError("rules must be a tuple of Rule instances")
    if not isinstance(timestamp, datetime):
        raise TypeError("timestamp must be a datetime")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
