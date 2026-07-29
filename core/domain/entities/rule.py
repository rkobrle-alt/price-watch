"""Rule entity."""

from dataclasses import dataclass
from uuid import UUID

from core.domain._validation import ensure_non_blank
from core.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class Rule:
    """An immutable named switch controlling a domain rule."""

    id: UUID
    name: str
    enabled: bool

    def __post_init__(self) -> None:
        """Validate rule invariants."""
        if not isinstance(self.id, UUID):
            raise ValidationError("rule id must be a UUID")
        ensure_non_blank(self.name, "rule name")
        if not isinstance(self.enabled, bool):
            raise ValidationError("enabled must be a bool")
