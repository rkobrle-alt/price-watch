"""Home Assistant App process boundary and outcome mapping."""

import os
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO
from uuid import UUID, uuid4

from applications.homeassistant.composition import (
    _HomeAssistantComposition,
    _compose_homeassistant,
)
from applications.homeassistant.configuration import parse_homeassistant_options
from applications.scheduler import IntervalScheduler
from applications.synchronization import SynchronizationResult
from core.configuration import ConfigurationError
from core.notifications import NotificationError
from core.rules import RuleError
from core.scheduler import Delay, SchedulerError
from core.state import StateStoreError
from infrastructure.configuration.json import JsonConfigurationLoader
from infrastructure.homeassistant import HomeAssistantError
from infrastructure.scheduler import SystemDelay

_DATA_DIRECTORY = Path("/data")
_OPTIONS_PATH = _DATA_DIRECTORY / "options.json"


def run(
    options: Mapping[str, object],
    access_token: str,
    stdout: TextIO,
    stderr: TextIO,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
    delay: Delay,
    *,
    data_directory: Path = _DATA_DIRECTORY,
    max_cycles: int | None = None,
) -> int:
    """Run the Supervisor-hosted monitor with explicit process dependencies."""
    _validate_dependencies(
        options,
        access_token,
        stdout,
        stderr,
        clock,
        notification_id_factory,
        delay,
        data_directory,
        max_cycles,
    )
    if not access_token.strip():
        _write(stderr, "error: SUPERVISOR_TOKEN cannot be blank\n")
        return 2
    try:
        config = parse_homeassistant_options(options, data_directory)
        composition = _compose_homeassistant(
            config,
            access_token,
            clock,
            notification_id_factory,
        )
    except (ConfigurationError, ValueError) as error:
        _write(stderr, f"error: {error}\n")
        return 2

    completed = 0
    provider_error_cycles = 0
    status_error_cycles = 0

    def cycle() -> None:
        nonlocal completed, provider_error_cycles, status_error_cycles
        result, status_published = _execute_cycle(
            composition,
            stdout,
            stderr,
            clock(),
        )
        completed += 1
        if result.provider_errors:
            provider_error_cycles += 1
        if not status_published:
            status_error_cycles += 1

    scheduler = IntervalScheduler(cycle, delay)
    try:
        result = scheduler.run(composition.interval, max_cycles)
    except KeyboardInterrupt:
        _write(
            stdout,
            "watch stopped: "
            f"cycles={completed} "
            f"provider_error_cycles={provider_error_cycles} "
            f"status_error_cycles={status_error_cycles}\n",
        )
        return 130
    except (StateStoreError, RuleError, NotificationError, SchedulerError) as error:
        _write(stderr, f"error: {error}\n")
        return 1

    _write(
        stdout,
        "watch complete: "
        f"cycles={result.cycles_completed} "
        f"provider_error_cycles={provider_error_cycles} "
        f"status_error_cycles={status_error_cycles}\n",
    )
    return 1 if provider_error_cycles or status_error_cycles else 0


def main() -> int:
    """Run from Supervisor-managed options, token and process facilities."""
    access_token = os.environ.get("SUPERVISOR_TOKEN")
    if access_token is None or not access_token.strip():
        _write(sys.stderr, "error: SUPERVISOR_TOKEN is required\n")
        return 2
    try:
        options = JsonConfigurationLoader().load(_OPTIONS_PATH)
    except ConfigurationError as error:
        _write(sys.stderr, f"error: {error}\n")
        return 2
    return run(
        options,
        access_token,
        sys.stdout,
        sys.stderr,
        lambda: datetime.now(UTC),
        uuid4,
        SystemDelay(),
        data_directory=_DATA_DIRECTORY,
    )


def _execute_cycle(
    composition: _HomeAssistantComposition,
    stdout: TextIO,
    stderr: TextIO,
    timestamp: datetime,
) -> tuple[SynchronizationResult, bool]:
    result = composition.workflow.run(composition.rules, timestamp)
    for error in result.provider_errors:
        _write(stderr, f"provider error: {error}\n")

    products = tuple(
        product
        for fetch_result in result.fetch_results
        for product in fetch_result.products
    )
    status_published = True
    try:
        composition.status_publisher.publish_cycle(
            products,
            timestamp,
            len(result.notifications),
            len(result.provider_errors),
        )
    except HomeAssistantError as error:
        status_published = False
        _write(stderr, f"status error: {error}\n")

    _write(
        stdout,
        "sync complete: "
        f"products={len(products)} "
        f"evaluations={len(result.evaluations)} "
        f"notifications={len(result.notifications)} "
        f"snapshots={len(result.snapshots)} "
        f"provider_errors={len(result.provider_errors)} "
        f"status_published={str(status_published).lower()}\n",
    )
    return result, status_published


def _validate_dependencies(
    options: object,
    access_token: object,
    stdout: object,
    stderr: object,
    clock: object,
    notification_id_factory: object,
    delay: object,
    data_directory: object,
    max_cycles: object,
) -> None:
    if not isinstance(options, Mapping):
        raise TypeError("options must be a Mapping")
    if not isinstance(access_token, str):
        raise TypeError("access_token must be a string")
    _validate_stream(stdout, "stdout")
    _validate_stream(stderr, "stderr")
    if not callable(clock):
        raise TypeError("clock must be callable")
    if not callable(notification_id_factory):
        raise TypeError("notification_id_factory must be callable")
    if not callable(getattr(delay, "wait", None)):
        raise TypeError("delay must expose a callable wait method")
    if not isinstance(data_directory, Path):
        raise TypeError("data_directory must be a Path")
    if max_cycles is not None:
        if isinstance(max_cycles, bool) or not isinstance(max_cycles, int):
            raise TypeError("max_cycles must be an int or None")
        if max_cycles <= 0:
            raise ValueError("max_cycles must be positive")


def _validate_stream(stream: object, name: str) -> None:
    if not callable(getattr(stream, "write", None)) or not callable(
        getattr(stream, "flush", None)
    ):
        raise TypeError(f"{name} must expose callable write and flush methods")


def _write(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()
