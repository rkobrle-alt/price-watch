"""Provider lifecycle statuses."""

from enum import StrEnum


class ProviderStatus(StrEnum):
    """Operational states available to a product provider."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    MAINTENANCE = "MAINTENANCE"
