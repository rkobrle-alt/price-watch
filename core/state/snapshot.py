"""Immutable product state snapshot."""

from dataclasses import dataclass
from datetime import datetime

from core.domain import Product


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """Capture a product state at a caller-supplied point in time."""

    product: Product
    timestamp: datetime

    def __post_init__(self) -> None:
        """Validate snapshot argument types and timestamp awareness."""
        if not isinstance(self.product, Product):
            raise TypeError("product must be a Product")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
