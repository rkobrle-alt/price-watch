"""Immutable Rule Engine evaluation result."""

from dataclasses import dataclass
from datetime import datetime

from core.rules.exceptions import RuleError


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Describe whether a rule matched and why at a caller-supplied time."""

    matched: bool
    reason: str
    timestamp: datetime

    def __post_init__(self) -> None:
        """Validate evaluation result invariants."""
        if not isinstance(self.matched, bool):
            raise RuleError("matched must be a bool")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise RuleError("reason cannot be empty")
        if not isinstance(self.timestamp, datetime):
            raise RuleError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise RuleError("timestamp must be timezone-aware")
