"""Operational health classifications."""

from enum import Enum


class OperationalHealthStatus(str, Enum):
    """Describe the durable health level of Price Watch."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class OperationalFailureKind(str, Enum):
    """Classify current operational failure evidence."""

    CATALOG_UNAVAILABLE = "catalog_unavailable"
    PROVIDER_DATA_INCOMPATIBLE = "provider_data_incompatible"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_FAILURE = "provider_failure"
    PARTIAL_PROVIDER_FAILURE = "partial_provider_failure"
    PROMOTION_UNAVAILABLE = "promotion_unavailable"
    DIGEST_DELIVERY_REJECTED = "digest_delivery_rejected"
    DIGEST_DELIVERY_UNCERTAIN = "digest_delivery_uncertain"


class OperationalNotificationKind(str, Enum):
    """Identify an incident transition notification."""

    FAILURE = "failure"
    RECOVERY = "recovery"
