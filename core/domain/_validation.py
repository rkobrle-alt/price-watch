"""Shared validation primitives internal to the domain package."""

from datetime import datetime

from core.domain.exceptions import ValidationError


def ensure_timezone_aware(value: datetime, field_name: str) -> None:
    """Ensure a datetime has a usable UTC offset."""
    if not isinstance(value, datetime):
        raise ValidationError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field_name} must be timezone-aware")


def ensure_non_blank(value: str, field_name: str) -> None:
    """Ensure a string contains at least one non-whitespace character."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} cannot be empty")
