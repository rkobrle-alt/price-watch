"""Operational monitoring exception contracts."""


class OperationalStateError(Exception):
    """Report operational-state persistence failures."""


class OperationalNotificationError(Exception):
    """Report operational-notification delivery failures."""
