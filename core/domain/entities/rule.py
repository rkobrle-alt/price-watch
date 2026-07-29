"""Rule entity."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from uuid import UUID

from core.domain._validation import ensure_non_blank
from core.domain.enums import RuleType
from core.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class Rule:
    """An immutable named switch controlling a domain rule."""

    id: UUID
    name: str
    enabled: bool
    rule_type: RuleType = RuleType.PRICE_DROP
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate rule invariants."""
        if not isinstance(self.id, UUID):
            raise ValidationError("rule id must be a UUID")
        ensure_non_blank(self.name, "rule name")
        if not isinstance(self.enabled, bool):
            raise ValidationError("enabled must be a bool")
        if not isinstance(self.rule_type, RuleType):
            raise ValidationError("rule_type must be a RuleType")
        if not isinstance(self.parameters, Mapping):
            raise ValidationError("parameters must be a mapping")
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(dict(self.parameters)),
        )
