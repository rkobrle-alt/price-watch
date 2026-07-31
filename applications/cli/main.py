"""Command dispatch and process outcome mapping for the Price Watch CLI."""

import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TextIO
from uuid import UUID, uuid4

from applications.cli.arguments import (
    SyncConfigurationArguments,
    VersionArguments,
    WatchArguments,
    WatchConfigurationArguments,
)
from applications.cli.composition import SyncComposition, compose_sync
from applications.cli.configuration import resolve_configured_command
from applications.cli.parser import ParserExit, parse_arguments
from applications.cli.version import VERSION
from applications.scheduler import IntervalScheduler
from applications.synchronization import SynchronizationResult
from core.configuration import ConfigurationError, ConfigurationLoader
from core.notifications import NotificationError
from core.rules import RuleError
from core.scheduler import Delay, SchedulerError
from core.state import StateStoreError
from infrastructure.configuration.toml import TomlConfigurationLoader
from infrastructure.scheduler import SystemDelay


def run(
    argv: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
    *,
    delay: Delay | None = None,
    configuration_loader: ConfigurationLoader | None = None,
) -> int:
    """Execute a CLI command using explicitly supplied process dependencies."""
    _validate_run_dependencies(
        argv,
        stdout,
        stderr,
        clock,
        notification_id_factory,
        delay,
        configuration_loader,
    )
    try:
        command = parse_arguments(argv, stdout, stderr)
    except ParserExit as completion:
        return completion.status

    if isinstance(command, VersionArguments):
        _write(stdout, f"Price Watch {VERSION}\n")
        return 0

    if isinstance(
        command,
        (SyncConfigurationArguments, WatchConfigurationArguments),
    ):
        if configuration_loader is None:
            raise TypeError("configuration_loader is required for --config")
        try:
            command = resolve_configured_command(command, configuration_loader)
        except ConfigurationError as error:
            _write(stderr, f"error: {error}\n")
            return 2

    sync_arguments = command.sync if isinstance(command, WatchArguments) else command
    try:
        composition = compose_sync(
            sync_arguments,
            stdout,
            clock,
            notification_id_factory,
        )
    except ValueError as error:
        _write(stderr, f"error: {error}\n")
        return 2

    if isinstance(command, WatchArguments):
        if delay is None:
            raise TypeError("delay is required for watch")
        return _run_watch(command, composition, stdout, stderr, clock, delay)
    return _run_sync(composition, stdout, stderr, clock)


def main() -> int:
    """Run the CLI using real command-line process dependencies."""
    return run(
        tuple(sys.argv[1:]),
        sys.stdout,
        sys.stderr,
        lambda: datetime.now(UTC),
        uuid4,
        delay=SystemDelay(),
        configuration_loader=TomlConfigurationLoader(),
    )


def _run_sync(
    composition: SyncComposition,
    stdout: TextIO,
    stderr: TextIO,
    clock: Callable[[], datetime],
) -> int:
    try:
        result = _execute_cycle(composition, stdout, stderr, clock())
    except (StateStoreError, RuleError, NotificationError) as error:
        _write(stderr, f"error: {error}\n")
        return 1
    return 1 if result.provider_errors else 0


def _run_watch(
    command: WatchArguments,
    composition: SyncComposition,
    stdout: TextIO,
    stderr: TextIO,
    clock: Callable[[], datetime],
    delay: Delay,
) -> int:
    completed = 0
    provider_error_cycles = 0

    def cycle() -> None:
        nonlocal completed, provider_error_cycles
        result = _execute_cycle(composition, stdout, stderr, clock())
        completed += 1
        if result.provider_errors:
            provider_error_cycles += 1

    scheduler = IntervalScheduler(cycle, delay)
    try:
        result = scheduler.run(command.interval, command.max_cycles)
    except KeyboardInterrupt:
        _write(
            stdout,
            "watch stopped: "
            f"cycles={completed} "
            f"provider_error_cycles={provider_error_cycles}\n",
        )
        return 130
    except (StateStoreError, RuleError, NotificationError, SchedulerError) as error:
        _write(stderr, f"error: {error}\n")
        return 1

    _write(
        stdout,
        "watch complete: "
        f"cycles={result.cycles_completed} "
        f"provider_error_cycles={provider_error_cycles}\n",
    )
    return 1 if provider_error_cycles else 0


def _execute_cycle(
    composition: SyncComposition,
    stdout: TextIO,
    stderr: TextIO,
    timestamp: datetime,
) -> SynchronizationResult:
    result = composition.workflow.run(composition.rules, timestamp)
    for error in result.provider_errors:
        _write(stderr, f"provider error: {error}\n")
    product_count = sum(
        len(fetch_result.products) for fetch_result in result.fetch_results
    )
    _write(
        stdout,
        "sync complete: "
        f"products={product_count} "
        f"evaluations={len(result.evaluations)} "
        f"notifications={len(result.notifications)} "
        f"snapshots={len(result.snapshots)} "
        f"provider_errors={len(result.provider_errors)}\n",
    )
    return result


def _validate_run_dependencies(
    argv: object,
    stdout: object,
    stderr: object,
    clock: object,
    notification_id_factory: object,
    delay: object,
    configuration_loader: object,
) -> None:
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence) or not all(
        isinstance(value, str) for value in argv
    ):
        raise TypeError("argv must be a sequence of strings")
    _validate_stream(stdout, "stdout")
    _validate_stream(stderr, "stderr")
    if not callable(clock):
        raise TypeError("clock must be callable")
    if not callable(notification_id_factory):
        raise TypeError("notification_id_factory must be callable")
    if delay is not None and not callable(getattr(delay, "wait", None)):
        raise TypeError("delay must expose a callable wait method or be None")
    if configuration_loader is not None and not callable(
        getattr(configuration_loader, "load", None)
    ):
        raise TypeError(
            "configuration_loader must expose a callable load method or be None"
        )


def _validate_stream(stream: object, name: str) -> None:
    if not callable(getattr(stream, "write", None)) or not callable(
        getattr(stream, "flush", None)
    ):
        raise TypeError(f"{name} must expose callable write and flush methods")


def _write(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()
