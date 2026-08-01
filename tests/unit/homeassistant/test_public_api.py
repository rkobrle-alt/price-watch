"""Public API and architecture tests for Home Assistant delivery."""

import ast
import inspect
from collections.abc import Mapping
from pathlib import Path

import infrastructure.homeassistant as homeassistant_api
import infrastructure.notifications.homeassistant as notification_api
from infrastructure.homeassistant import (
    HomeAssistantClient,
    HomeAssistantError,
    UrllibHomeAssistantClient,
)
from infrastructure.notifications.homeassistant import (
    HomeAssistantNotificationChannel,
)


class FakeClient:
    """Structurally implement the Home Assistant client contract."""

    def call_service(
        self,
        domain: str,
        service: str,
        data: Mapping[str, object],
    ) -> None:
        """Accept one service call."""


def test_homeassistant_public_apis_are_explicit_and_documented() -> None:
    assert homeassistant_api.__all__ == [
        "HomeAssistantClient",
        "HomeAssistantError",
        "UrllibHomeAssistantClient",
    ]
    assert notification_api.__all__ == ["HomeAssistantNotificationChannel"]
    assert homeassistant_api.HomeAssistantClient is HomeAssistantClient
    assert homeassistant_api.HomeAssistantError is HomeAssistantError
    assert homeassistant_api.UrllibHomeAssistantClient is UrllibHomeAssistantClient
    assert (
        notification_api.HomeAssistantNotificationChannel
        is HomeAssistantNotificationChannel
    )
    assert isinstance(FakeClient(), HomeAssistantClient)
    for public_object in (
        HomeAssistantClient,
        HomeAssistantError,
        UrllibHomeAssistantClient,
        HomeAssistantNotificationChannel,
    ):
        assert inspect.getdoc(public_object)


def test_homeassistant_dependency_direction_and_secret_boundary() -> None:
    root = Path(__file__).parents[3]
    homeassistant = root / "infrastructure" / "homeassistant"
    notification = root / "infrastructure" / "notifications" / "homeassistant"
    imports = _package_imports(homeassistant)
    notification_imports = _package_imports(notification)

    assert not any(name.startswith("applications") for name in imports)
    assert not any(name.startswith("core") for name in imports)
    assert not any(name.startswith("applications") for name in notification_imports)
    for package in (homeassistant, notification):
        for module in package.rglob("*.py"):
            source = module.read_text(encoding="utf-8")
            assert "SUPERVISOR_TOKEN" not in source
            assert "os.environ" not in source
            assert "smtp" not in source.casefold()


def _package_imports(package: Path) -> set[str]:
    imports: set[str] = set()
    for module in package.rglob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module)
    return imports
