"""Product identifier value object."""

from dataclasses import dataclass
from uuid import UUID

from core.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class ProductId:
    """A strongly typed UUID identifying a product."""

    value: UUID

    def __post_init__(self) -> None:
        """Validate the wrapped identifier."""
        if not isinstance(self.value, UUID):
            raise ValidationError("product id must be a UUID")
