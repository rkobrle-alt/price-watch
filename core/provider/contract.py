"""Structural contract implemented by product providers."""

from collections.abc import Callable
from typing import Protocol

from core.domain import ProviderId
from core.provider.result import FetchResult


class Provider(Protocol):
    """Transport-neutral contract for a source of domain products."""

    id: ProviderId
    display_name: str
    version: str
    fetch: Callable[[], FetchResult]
