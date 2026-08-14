"""Immutable operational monitoring values."""

from dataclasses import dataclass
from datetime import date, datetime

from core.operations.enums import (
    OperationalFailureKind,
    OperationalHealthStatus,
    OperationalNotificationKind,
)


@dataclass(frozen=True, slots=True)
class OperationalCheck:
    """Represent one timestamped operational health observation."""

    timestamp: datetime
    failure_kind: OperationalFailureKind | None = None

    def __post_init__(self) -> None:
        """Validate check types and timestamp awareness."""
        _validate_timestamp(self.timestamp, "timestamp")
        if self.failure_kind is not None and not isinstance(
            self.failure_kind,
            OperationalFailureKind,
        ):
            raise TypeError(
                "failure_kind must be an OperationalFailureKind or None"
            )


@dataclass(frozen=True, slots=True)
class DailyDigestDelivery:
    """Retain diagnostics for one successfully delivered daily digest."""

    calendar_date: date
    delivered_at: datetime
    product_count: int
    promotion_included: bool

    def __post_init__(self) -> None:
        """Validate exact delivery diagnostics."""
        if not isinstance(self.calendar_date, date) or isinstance(
            self.calendar_date,
            datetime,
        ):
            raise TypeError("calendar_date must be a date")
        _validate_timestamp(self.delivered_at, "delivered_at")
        _validate_count(self.product_count, "product_count")
        if not isinstance(self.promotion_included, bool):
            raise TypeError("promotion_included must be a bool")


@dataclass(frozen=True, slots=True)
class OperationalNotification:
    """Describe one channel-neutral operational transition message."""

    kind: OperationalNotificationKind
    message: str
    created_at: datetime

    def __post_init__(self) -> None:
        """Validate notification content without side effects."""
        if not isinstance(self.kind, OperationalNotificationKind):
            raise TypeError("kind must be an OperationalNotificationKind")
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")
        if not self.message.strip():
            raise ValueError("message cannot be blank")
        _validate_timestamp(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class OperationalState:
    """Retain durable operational health and digest diagnostics."""

    status: OperationalHealthStatus
    failure_kind: OperationalFailureKind | None
    consecutive_failure_cycles: int
    incident_started_at: datetime | None
    last_checked_at: datetime | None
    last_recovered_at: datetime | None
    incident_notified: bool
    pending_notification: OperationalNotificationKind | None
    last_digest_delivery: DailyDigestDelivery | None

    def __post_init__(self) -> None:
        """Validate the complete operational-state invariant."""
        if not isinstance(self.status, OperationalHealthStatus):
            raise TypeError("status must be an OperationalHealthStatus")
        if self.failure_kind is not None and not isinstance(
            self.failure_kind,
            OperationalFailureKind,
        ):
            raise TypeError(
                "failure_kind must be an OperationalFailureKind or None"
            )
        _validate_count(
            self.consecutive_failure_cycles,
            "consecutive_failure_cycles",
        )
        for value, name in (
            (self.incident_started_at, "incident_started_at"),
            (self.last_checked_at, "last_checked_at"),
            (self.last_recovered_at, "last_recovered_at"),
        ):
            if value is not None:
                _validate_timestamp(value, name)
        if not isinstance(self.incident_notified, bool):
            raise TypeError("incident_notified must be a bool")
        if self.pending_notification is not None and not isinstance(
            self.pending_notification,
            OperationalNotificationKind,
        ):
            raise TypeError(
                "pending_notification must be an OperationalNotificationKind or None"
            )
        if self.last_digest_delivery is not None and not isinstance(
            self.last_digest_delivery,
            DailyDigestDelivery,
        ):
            raise TypeError(
                "last_digest_delivery must be a DailyDigestDelivery or None"
            )
        self._validate_health_invariant()
        self._validate_chronology()

    @classmethod
    def initial(cls) -> "OperationalState":
        """Return the canonical initial healthy state."""
        return cls(
            OperationalHealthStatus.OK,
            None,
            0,
            None,
            None,
            None,
            False,
            None,
            None,
        )

    def _validate_health_invariant(self) -> None:
        if self.status is OperationalHealthStatus.OK:
            if self.failure_kind is not None or self.consecutive_failure_cycles:
                raise ValueError("ok state cannot contain current failure data")
        elif (
            self.failure_kind is None
            or self.consecutive_failure_cycles == 0
            or self.incident_started_at is None
            or self.last_checked_at is None
        ):
            raise ValueError("unhealthy state requires complete failure data")
        if self.status is OperationalHealthStatus.DEGRADED and (
            self.incident_notified or self.pending_notification is not None
        ):
            raise ValueError("degraded state cannot contain notification state")
        if self.pending_notification is OperationalNotificationKind.FAILURE and (
            self.status is not OperationalHealthStatus.FAILED
            or self.incident_notified
        ):
            raise ValueError("pending failure requires an unnotified failed state")
        if self.pending_notification is OperationalNotificationKind.RECOVERY and (
            self.status is not OperationalHealthStatus.OK
            or not self.incident_notified
            or self.incident_started_at is None
            or self.last_recovered_at is None
        ):
            raise ValueError("pending recovery requires a notified recovered state")
        if self.status is OperationalHealthStatus.OK and (
            self.incident_started_at is not None
            or self.incident_notified
        ) and self.pending_notification is not OperationalNotificationKind.RECOVERY:
            raise ValueError("ok incident data requires a pending recovery")

    def _validate_chronology(self) -> None:
        if (
            self.incident_started_at is not None
            and self.last_checked_at is not None
            and self.incident_started_at > self.last_checked_at
        ):
            raise ValueError("incident_started_at cannot follow last_checked_at")
        if (
            self.last_recovered_at is not None
            and self.last_checked_at is not None
            and self.last_recovered_at > self.last_checked_at
        ):
            raise ValueError("last_recovered_at cannot follow last_checked_at")


def _validate_timestamp(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _validate_count(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
