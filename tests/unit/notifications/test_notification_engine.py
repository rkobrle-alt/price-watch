"""Unit tests for deterministic notification generation."""

from unittest import TestCase

from core.domain import Notification
from core.notifications import NotificationEngine
from tests.unit.notifications.helpers import (
    NOTIFICATION_ID,
    PRODUCT_ID,
    TIMESTAMP,
    create_evaluation,
    create_product,
)


class NotificationEngineTests(TestCase):
    """Verify pure conversion of evaluation results into notifications."""

    def setUp(self) -> None:
        """Create deterministic inputs and a stateless engine."""
        self.engine = NotificationEngine()
        self.product = create_product()
        self.evaluation = create_evaluation()

    def test_matching_evaluation_generates_notification(self) -> None:
        result = self.engine.generate(
            self.product,
            self.evaluation,
            NOTIFICATION_ID,
        )

        self.assertIsInstance(result, Notification)
        self.assertEqual(result.id, NOTIFICATION_ID)
        self.assertEqual(result.product_id, PRODUCT_ID)
        self.assertEqual(result.message, self.evaluation.reason)
        self.assertEqual(result.created_at, TIMESTAMP)

    def test_non_matching_evaluation_returns_none(self) -> None:
        result = self.engine.generate(
            self.product,
            create_evaluation(matched=False),
            NOTIFICATION_ID,
        )

        self.assertIsNone(result)

    def test_invalid_argument_types_raise_type_error(self) -> None:
        cases = (
            ("product", create_evaluation(), NOTIFICATION_ID, "product"),
            (self.product, "evaluation", NOTIFICATION_ID, "evaluation"),
            (self.product, self.evaluation, "id", "notification_id"),
        )

        for product, evaluation, notification_id, expected_message in cases:
            with self.subTest(argument=expected_message):
                with self.assertRaisesRegex(TypeError, expected_message):
                    self.engine.generate(  # type: ignore[arg-type]
                        product,
                        evaluation,
                        notification_id,
                    )

    def test_equal_inputs_produce_equal_notifications(self) -> None:
        first = self.engine.generate(
            self.product,
            self.evaluation,
            NOTIFICATION_ID,
        )
        second = self.engine.generate(
            self.product,
            self.evaluation,
            NOTIFICATION_ID,
        )

        self.assertEqual(first, second)
