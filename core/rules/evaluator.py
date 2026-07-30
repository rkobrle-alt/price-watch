"""Structural contract for independent rule evaluators."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from core.domain import Product, Rule, RuleType
from core.rules.evaluation import EvaluationResult


class RuleEvaluator(Protocol):
    """Contract implemented by one RuleType-specific evaluator."""

    rule_type: RuleType
    evaluate: Callable[
        [Rule, Product | None, Product, datetime],
        EvaluationResult,
    ]
