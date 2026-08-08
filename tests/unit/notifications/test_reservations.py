"""Tests for immutable notification reservation contracts and policy."""

from datetime import datetime
from decimal import Decimal
from typing import cast

import pytest

from core.domain import Currency, Money, Product, ProductId, Rule, RuleType
from core.notifications import (
    NotificationReservation,
    NotificationReservationError,
    NotificationReservationStore,
    PriceDropReservationPolicy,
)
from core.rules import EvaluationResult
from tests.unit.notifications.helpers import (
    PRODUCT_ID,
    TIMESTAMP,
    create_evaluation,
    create_product,
)
from tests.unit.rules.helpers import create_rule


class _Store:
    def reserve(
        self,
        reservation: NotificationReservation,
        reserved_at: datetime,
    ) -> bool:
        return True

    def release(self, reservation: NotificationReservation) -> None:
        return None


def test_reservation_store_protocol_is_structural() -> None:
    store: NotificationReservationStore = _Store()

    assert store.reserve(_reservation(), TIMESTAMP)
    assert store.release(_reservation()) is None


def test_reservation_is_immutable_and_keeps_exact_price() -> None:
    reservation = _reservation()

    assert reservation.product_id == PRODUCT_ID
    assert reservation.rule_type is RuleType.PRICE_DROP
    assert reservation.price == Money(Decimal("99.90"), Currency.CZK)
    with pytest.raises(AttributeError):
        reservation.price = Money(Decimal("1"), Currency.CZK)  # type: ignore[misc]


@pytest.mark.parametrize(
    "values",
    [
        {"product_id": object()},
        {"rule_type": object()},
        {"price": object()},
    ],
)
def test_reservation_rejects_invalid_member_types(values: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "product_id": PRODUCT_ID,
        "rule_type": RuleType.PRICE_DROP,
        "price": Money(Decimal("1"), Currency.CZK),
    }
    arguments.update(values)

    with pytest.raises(TypeError):
        NotificationReservation(**arguments)  # type: ignore[arg-type]


def test_price_drop_policy_creates_stable_matching_identity() -> None:
    product = create_product()
    rule = create_rule(RuleType.PRICE_DROP)

    result = PriceDropReservationPolicy().create(
        rule,
        product,
        create_evaluation(),
    )

    assert result == NotificationReservation(
        product.id,
        RuleType.PRICE_DROP,
        product.current_price,
    )


@pytest.mark.parametrize(
    ("rule", "evaluation"),
    [
        (create_rule(RuleType.PRICE_DROP, enabled=False), create_evaluation()),
        (create_rule(RuleType.BACK_IN_STOCK), create_evaluation()),
        (create_rule(RuleType.PRICE_DROP), create_evaluation(matched=False)),
    ],
)
def test_price_drop_policy_ignores_non_alerts(
    rule: Rule,
    evaluation: EvaluationResult,
) -> None:
    assert (
        PriceDropReservationPolicy().create(rule, create_product(), evaluation)
        is None
    )


@pytest.mark.parametrize(
    ("rule", "product", "evaluation"),
    [
        (object(), create_product(), create_evaluation()),
        (create_rule(RuleType.PRICE_DROP), object(), create_evaluation()),
        (create_rule(RuleType.PRICE_DROP), create_product(), object()),
    ],
)
def test_price_drop_policy_rejects_invalid_types(
    rule: object,
    product: object,
    evaluation: object,
) -> None:
    with pytest.raises(TypeError):
        PriceDropReservationPolicy().create(
            cast(Rule, rule),
            cast(Product, product),
            cast(EvaluationResult, evaluation),
        )


def test_reservation_error_is_public_runtime_error() -> None:
    assert issubclass(NotificationReservationError, Exception)


def _reservation() -> NotificationReservation:
    return NotificationReservation(
        cast(ProductId, PRODUCT_ID),
        RuleType.PRICE_DROP,
        Money(Decimal("99.90"), Currency.CZK),
    )
