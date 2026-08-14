"""Restart-spanning operational incident and recovery integration test."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from applications.operational_monitoring import OperationalMonitoringWorkflow
from core.operations import (
    DailyDigestDelivery,
    OperationalCheck,
    OperationalFailureKind,
    OperationalHealthEngine,
    OperationalHealthStatus,
    OperationalNotificationKind,
)
from infrastructure.homeassistant import (
    HomeAssistantOperationalNotificationChannel,
)
from infrastructure.persistence.sqlite import SqliteOperationalStateStore

_NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)


class _RecordingHomeAssistantClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, object]]] = []

    def call_service(
        self,
        domain: str,
        service: str,
        data: Mapping[str, object],
    ) -> None:
        self.calls.append((domain, service, data))


def _workflow(
    path: Path,
    client: _RecordingHomeAssistantClient,
) -> OperationalMonitoringWorkflow:
    return OperationalMonitoringWorkflow(
        SqliteOperationalStateStore(path),
        OperationalHealthEngine(),
        HomeAssistantOperationalNotificationChannel(
            client,
            "notify.gmail_parkside",
            "Parkside Catalog",
        ),
    )


def test_incident_digest_and_recovery_survive_process_recomposition(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    client = _RecordingHomeAssistantClient()
    delivery = DailyDigestDelivery(date(2026, 8, 14), _NOW, 12, True)

    first = _workflow(path, client).run(
        OperationalCheck(
            _NOW,
            OperationalFailureKind.PROVIDER_UNAVAILABLE,
        ),
        delivery,
    )
    second = _workflow(path, client).run(
        OperationalCheck(
            _NOW + timedelta(minutes=5),
            OperationalFailureKind.PROVIDER_UNAVAILABLE,
        )
    )
    failed = _workflow(path, client).run(
        OperationalCheck(
            _NOW + timedelta(minutes=10),
            OperationalFailureKind.PROVIDER_UNAVAILABLE,
        )
    )
    continued = _workflow(path, client).run(
        OperationalCheck(
            _NOW + timedelta(minutes=15),
            OperationalFailureKind.PROVIDER_UNAVAILABLE,
        )
    )
    recovered = _workflow(path, client).run(
        OperationalCheck(_NOW + timedelta(minutes=20))
    )

    assert first.state.status is OperationalHealthStatus.DEGRADED
    assert second.state.consecutive_failure_cycles == 2
    assert failed.notification_sent is OperationalNotificationKind.FAILURE
    assert continued.notification_sent is None
    assert recovered.notification_sent is OperationalNotificationKind.RECOVERY
    assert len(client.calls) == 2
    assert client.calls[0][2]["title"] == (
        "Parkside Catalog Operational Health"
    )
    assert "operational failure" in str(client.calls[0][2]["message"])
    assert "operational recovery" in str(client.calls[1][2]["message"])

    persisted = SqliteOperationalStateStore(path).load()
    assert persisted.status is OperationalHealthStatus.OK
    assert persisted.last_digest_delivery == delivery
    assert persisted.incident_started_at is None
    assert persisted.pending_notification is None
