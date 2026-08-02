"""Standard-library Home Assistant REST client."""

import json
import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from infrastructure.homeassistant.exceptions import HomeAssistantError

_IDENTIFIER_PATTERN = re.compile(r"[a-z0-9_]+")
_SENSOR_ENTITY_PATTERN = re.compile(r"sensor\.[a-z0-9_]+")


class UrllibHomeAssistantClient:
    """Call Home Assistant Core services and publish state through its REST API."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        timeout_seconds: int = 10,
        user_agent: str = "PriceWatch/0.12",
        opener: Callable[..., AbstractContextManager[BinaryIO]] = urlopen,
    ) -> None:
        """Configure the explicit API endpoint, credentials and HTTP boundary."""
        self._base_url = _validate_base_url(base_url)
        self._access_token = _validate_text(access_token, "access_token")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            raise TypeError("timeout_seconds must be an int")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._user_agent = _validate_text(user_agent, "user_agent")
        if not callable(opener):
            raise TypeError("opener must be callable")
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def call_service(
        self,
        domain: str,
        service: str,
        data: Mapping[str, object],
    ) -> None:
        """POST one deterministic JSON service call to Home Assistant Core."""
        _validate_identifier(domain, "domain")
        _validate_identifier(service, "service")
        _validate_mapping(data, "data")

        self._post_json(
            f"{self._base_url}/services/{domain}/{service}",
            data,
            f"Home Assistant service call failed: {domain}.{service}",
        )

    def set_state(
        self,
        entity_id: str,
        state: str,
        attributes: Mapping[str, object],
    ) -> None:
        """Create or update one Home Assistant sensor state representation."""
        _validate_sensor_entity_id(entity_id)
        state_text = _validate_text(state, "state")
        _validate_mapping(attributes, "attributes")

        self._post_json(
            f"{self._base_url}/states/{entity_id}",
            {
                "attributes": dict(attributes),
                "state": state_text,
            },
            f"Home Assistant state update failed: {entity_id}",
        )

    def _post_json(
        self,
        endpoint: str,
        data: Mapping[str, object],
        failure_message: str,
    ) -> None:
        body = json.dumps(
            dict(data),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
                "User-Agent": self._user_agent,
            },
            method="POST",
        )
        try:
            with self._opener(
                request,
                timeout=self._timeout_seconds,
            ) as response:
                response.read()
        except (HTTPError, URLError, OSError) as error:
            raise HomeAssistantError(failure_message) from error


def _validate_base_url(value: object) -> str:
    text = _validate_text(value, "base_url")
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute HTTP or HTTPS URL")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url cannot contain a query or fragment")
    return text.rstrip("/")


def _validate_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} cannot be blank")
    return value


def _validate_identifier(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{name} must contain only lowercase ASCII letters, digits and underscores"
        )


def _validate_sensor_entity_id(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError("entity_id must be a string")
    if _SENSOR_ENTITY_PATTERN.fullmatch(value) is None:
        raise ValueError("entity_id must be a lowercase sensor entity ID")


def _validate_mapping(value: object, name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a Mapping")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"{name} keys must be strings")
