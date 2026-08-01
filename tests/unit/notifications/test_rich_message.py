"""Tests for actionable channel-neutral notification messages."""

from dataclasses import replace

from core.notifications import NotificationEngine
from tests.unit.notifications.helpers import (
    NOTIFICATION_ID,
    create_evaluation,
    create_product,
)


def test_unavailable_product_message_uses_exact_actionable_content() -> None:
    product = replace(create_product(), availability=False)

    notification = NotificationEngine().generate(
        product,
        create_evaluation(),
        NOTIFICATION_ID,
    )

    assert notification is not None
    assert notification.message == (
        "Product price decreased.\n"
        "Product: Coffee\n"
        "Current price: 99.90 CZK\n"
        "Availability: unavailable\n"
        "URL: https://example.test/product"
    )
