"""Price watch rule types."""

from enum import StrEnum


class RuleType(StrEnum):
    """Kinds of rules supported by the domain."""

    PRICE_DROP = "PRICE_DROP"
    BACK_IN_STOCK = "BACK_IN_STOCK"
