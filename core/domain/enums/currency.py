"""Currencies supported by the Price Watch domain."""

from enum import StrEnum


class Currency(StrEnum):
    """ISO 4217 currencies supported by the platform."""

    CZK = "CZK"
    EUR = "EUR"
    USD = "USD"
    PLN = "PLN"
