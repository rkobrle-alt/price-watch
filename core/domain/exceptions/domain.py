"""Exceptions raised by domain operations and validation."""


class DomainError(Exception):
    """Base exception for all Price Watch domain errors."""


class ValidationError(DomainError):
    """Raised when a domain object cannot satisfy its invariants."""
