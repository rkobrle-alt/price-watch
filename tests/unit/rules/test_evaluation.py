"""Unit tests for immutable evaluation results."""

from dataclasses import FrozenInstanceError
from datetime import datetime
from unittest import TestCase

from core.rules import EvaluationResult, RuleError
from tests.unit.rules.helpers import TIMESTAMP


class EvaluationResultTests(TestCase):
    """Verify evaluation result invariants and immutability."""

    def test_contains_result_explanation_and_timestamp(self) -> None:
        result = EvaluationResult(True, "Rule matched.", TIMESTAMP)

        self.assertTrue(result.matched)
        self.assertEqual(result.reason, "Rule matched.")
        self.assertEqual(result.timestamp, TIMESTAMP)
        with self.assertRaises(FrozenInstanceError):
            result.matched = False  # type: ignore[misc]

    def test_rejects_non_boolean_match(self) -> None:
        with self.assertRaisesRegex(RuleError, "matched must be a bool"):
            EvaluationResult(1, "Invalid.", TIMESTAMP)  # type: ignore[arg-type]

    def test_rejects_empty_or_non_string_reason(self) -> None:
        for reason in ("", "  ", 1):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(RuleError, "reason cannot be empty"):
                    EvaluationResult(False, reason, TIMESTAMP)  # type: ignore[arg-type]

    def test_rejects_non_datetime_timestamp(self) -> None:
        with self.assertRaisesRegex(RuleError, "must be a datetime"):
            EvaluationResult(False, "Invalid.", "now")  # type: ignore[arg-type]

    def test_rejects_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(RuleError, "must be timezone-aware"):
            EvaluationResult(False, "Invalid.", datetime(2026, 7, 30))
