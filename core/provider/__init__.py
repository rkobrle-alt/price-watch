"""Public API for the transport-neutral Provider SDK."""

from core.provider.contract import Provider
from core.provider.error import ProviderError
from core.provider.metadata import ProviderMetadata
from core.provider.registry import ProviderRegistry
from core.provider.result import FetchResult

__all__ = [
    "FetchResult",
    "Provider",
    "ProviderError",
    "ProviderMetadata",
    "ProviderRegistry",
]
