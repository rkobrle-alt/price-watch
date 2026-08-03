"""Immutable product catalog reference."""

from dataclasses import dataclass

from core.domain import ProviderId


@dataclass(frozen=True, slots=True)
class ProductReference:
    """Identify one provider product without creating a Domain product."""

    provider_id: ProviderId
    external_id: str
    url: str

    def __post_init__(self) -> None:
        """Validate the provider identity and canonical reference values."""
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be a ProviderId")
        _validate_non_blank_string(self.external_id, "external_id")
        _validate_non_blank_string(self.url, "url")


def _validate_non_blank_string(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    if not value.strip():
        raise ValueError(f"{name} cannot be blank")
