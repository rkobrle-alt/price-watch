"""Provider identifier value object."""

from dataclasses import dataclass
from uuid import UUID

from core.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class ProviderId:
    """A strongly typed UUID identifying a provider."""

    value: UUID

    def __post_init__(self) -> None:
        """Validate the wrapped identifier."""
        if not isinstance(self.value, UUID):
            raise ValidationError("provider id must be a UUID")
