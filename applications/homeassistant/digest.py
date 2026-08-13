"""Home Assistant composition helper for the optional daily digest."""

from pathlib import Path
from zoneinfo import ZoneInfo

from applications.daily_digest import (
    DailyDigestConfig,
    DailyDigestWorkflow,
)
from core.notifications import DailyDiscountDigestEngine
from core.promotions import DailyPromotionSource
from infrastructure.homeassistant import HomeAssistantClient
from infrastructure.notifications.homeassistant import (
    HomeAssistantDailyDiscountDigestChannel,
)
from infrastructure.persistence.sqlite import (
    SqliteDailyDigestReservationStore,
    SqliteStateStore,
)


def compose_daily_digest(
    config: DailyDigestConfig | None,
    state_store: SqliteStateStore,
    database_file: Path,
    client: HomeAssistantClient,
    notify_entity: str,
    notification_title: str,
    promotion_source: DailyPromotionSource | None = None,
) -> DailyDigestWorkflow | None:
    """Compose the optional catalog digest with shared durable state."""
    if config is None:
        return None
    channel = HomeAssistantDailyDiscountDigestChannel(
        client,
        notify_entity,
        f"{notification_title} Daily Digest",
    )
    return DailyDigestWorkflow(
        state_store,
        SqliteDailyDigestReservationStore(database_file),
        DailyDiscountDigestEngine(),
        channel,
        config,
        _prague_timezone(),
        promotion_source=promotion_source,
    )


def _prague_timezone() -> ZoneInfo:
    return ZoneInfo("Europe/Prague")
