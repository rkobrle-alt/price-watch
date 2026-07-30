"""Structural contract for product state storage."""

from collections.abc import Callable
from typing import Protocol

from core.domain import ProductId
from core.state.snapshot import StateSnapshot


class StateStore(Protocol):
    """Contract for loading and saving the latest product snapshot."""

    load: Callable[[ProductId], StateSnapshot | None]
    save: Callable[[StateSnapshot], None]
