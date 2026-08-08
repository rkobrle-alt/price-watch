"""Private optional reference and reservation coordination."""

from collections.abc import Callable
from datetime import datetime
from typing import cast
from uuid import UUID

from core.domain import Notification, Product, Rule
from core.notifications import (
    NotificationChannel,
    NotificationEngine,
    NotificationReservation,
    NotificationReservationStore,
    PriceDropReservationPolicy,
)
from core.rules import EvaluationResult, PriceReferencePolicy
from core.state import ObservationHistory, StateSnapshot


class _AlertCoordinator:
    """Coordinate optional history enrichment and price-alert reservation."""

    def __init__(
        self,
        notification_engine: NotificationEngine,
        notification_channel: NotificationChannel,
        notification_id_factory: Callable[[], UUID],
        observation_history: ObservationHistory | None,
        price_reference_policy: PriceReferencePolicy | None,
        notification_reservation_store: NotificationReservationStore | None,
        price_drop_reservation_policy: PriceDropReservationPolicy | None,
    ) -> None:
        _validate_optional_pair(
            observation_history,
            price_reference_policy,
            ("history",),
            ("enrich",),
            "observation history and price reference policy",
        )
        _validate_optional_pair(
            notification_reservation_store,
            price_drop_reservation_policy,
            ("reserve", "release"),
            ("create",),
            "notification reservation store and policy",
        )
        self._notification_engine = notification_engine
        self._notification_channel = notification_channel
        self._notification_id_factory = notification_id_factory
        self._observation_history = cast(
            ObservationHistory | None,
            observation_history,
        )
        self._price_reference_policy = cast(
            PriceReferencePolicy | None,
            price_reference_policy,
        )
        self._reservation_store = cast(
            NotificationReservationStore | None,
            notification_reservation_store,
        )
        self._reservation_policy = cast(
            PriceDropReservationPolicy | None,
            price_drop_reservation_policy,
        )

    def enrich(self, product: Product) -> Product:
        """Apply the configured deterministic history policy."""
        if self._observation_history is None:
            return product
        history = self._observation_history.history(product.id)
        if not isinstance(history, tuple) or not all(
            isinstance(snapshot, StateSnapshot) for snapshot in history
        ):
            raise TypeError(
                "observation history must return a tuple of StateSnapshot values"
            )
        policy = cast(PriceReferencePolicy, self._price_reference_policy)
        enriched = policy.enrich(product, history)
        if not isinstance(enriched, Product):
            raise TypeError("price reference policy must return a Product")
        return enriched

    def notify(
        self,
        rule: Rule,
        product: Product,
        evaluation: EvaluationResult,
        timestamp: datetime,
    ) -> tuple[Notification | None, bool]:
        """Reserve, generate and deliver one evaluation notification."""
        reservation = self._create_reservation(rule, product, evaluation)
        if reservation is not None and not self._reserve(reservation, timestamp):
            return None, True
        notification = self._generate_and_send(
            product,
            evaluation,
            reservation,
        )
        return notification, False

    def _create_reservation(
        self,
        rule: Rule,
        product: Product,
        evaluation: EvaluationResult,
    ) -> NotificationReservation | None:
        if self._reservation_policy is None:
            return None
        reservation = self._reservation_policy.create(rule, product, evaluation)
        if reservation is not None and not isinstance(
            reservation,
            NotificationReservation,
        ):
            raise TypeError(
                "price drop reservation policy must return "
                "a NotificationReservation or None"
            )
        return reservation

    def _reserve(
        self,
        reservation: NotificationReservation,
        timestamp: datetime,
    ) -> bool:
        store = cast(NotificationReservationStore, self._reservation_store)
        reserved = store.reserve(reservation, timestamp)
        if not isinstance(reserved, bool):
            raise TypeError("notification reservation store must return a bool")
        return reserved

    def _generate_and_send(
        self,
        product: Product,
        evaluation: EvaluationResult,
        reservation: NotificationReservation | None,
    ) -> Notification | None:
        try:
            notification = self._notification_engine.generate(
                product,
                evaluation,
                self._notification_id_factory(),
            )
        except Exception:
            if reservation is not None:
                self._release(reservation)
            raise
        if notification is None:
            if reservation is not None:
                self._release(reservation)
            return None
        try:
            self._notification_channel.send(notification)
        except Exception:
            if reservation is not None:
                self._release(reservation)
            raise
        return notification

    def _release(self, reservation: NotificationReservation) -> None:
        store = cast(NotificationReservationStore, self._reservation_store)
        store.release(reservation)


def _validate_optional_pair(
    first: object | None,
    second: object | None,
    first_methods: tuple[str, ...],
    second_methods: tuple[str, ...],
    name: str,
) -> None:
    if (first is None) != (second is None):
        raise ValueError(f"{name} must be supplied together")
    if first is not None:
        _validate_methods(first, first_methods, name)
        _validate_methods(second, second_methods, name)


def _validate_methods(
    dependency: object,
    methods: tuple[str, ...],
    name: str,
) -> None:
    for method in methods:
        if not callable(getattr(dependency, method, None)):
            raise TypeError(f"{name} must expose a callable {method} method")
