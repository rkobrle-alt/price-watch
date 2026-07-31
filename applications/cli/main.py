"""Command dispatch and process outcome mapping for the Price Watch CLI."""

import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TextIO
from uuid import UUID, uuid4

from applications.cli.arguments import VersionArguments
from applications.cli.composition import compose_sync
from applications.cli.parser import ParserExit, parse_arguments
from applications.cli.version import VERSION
from core.notifications import NotificationError
from core.rules import RuleError
from core.state import StateStoreError


def run(
    argv: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    clock: Callable[[], datetime],
    notification_id_factory: Callable[[], UUID],
) -> int:
    """Execute a CLI command using explicitly supplied process dependencies."""
    _validate_run_dependencies(
        argv,
        stdout,
        stderr,
        clock,
        notification_id_factory,
    )
    try:
        command = parse_arguments(argv, stdout, stderr)
    except ParserExit as completion:
        return completion.status

    if isinstance(command, VersionArguments):
        _write(stdout, f"Price Watch {VERSION}\n")
        return 0

    try:
        composition = compose_sync(
            command,
            stdout,
            clock,
            notification_id_factory,
        )
    except ValueError as error:
        _write(stderr, f"error: {error}\n")
        return 2

    timestamp = clock()
    try:
        result = composition.workflow.run(composition.rules, timestamp)
    except (StateStoreError, RuleError, NotificationError) as error:
        _write(stderr, f"error: {error}\n")
        return 1

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
    return 1 if result.provider_errors else 0


def main() -> int:
    """Run the CLI using real command-line process dependencies."""
    return run(
        tuple(sys.argv[1:]),
        sys.stdout,
        sys.stderr,
        lambda: datetime.now(UTC),
        uuid4,
    )


def _validate_run_dependencies(
    argv: object,
    stdout: object,
    stderr: object,
    clock: object,
    notification_id_factory: object,
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


def _validate_stream(stream: object, name: str) -> None:
    if not callable(getattr(stream, "write", None)) or not callable(
        getattr(stream, "flush", None)
    ):
        raise TypeError(f"{name} must expose callable write and flush methods")


def _write(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()
