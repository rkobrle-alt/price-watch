"""Provider entity."""

from dataclasses import dataclass

from core.domain._validation import ensure_non_blank
from core.domain.value_objects import ProviderId


@dataclass(frozen=True, slots=True)
class Provider:
    """An immutable source from which product information is obtained."""

    id: ProviderId
    name: str
    country: str
    website: str

    def __post_init__(self) -> None:
        """Validate provider invariants."""
        ensure_non_blank(self.name, "provider name")
