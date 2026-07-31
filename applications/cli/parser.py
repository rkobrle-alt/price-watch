"""Standard-library command-line parser with injected output streams."""

import argparse
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

from applications.cli.arguments import (
    CliArguments,
    SyncArguments,
    VersionArguments,
    WatchArguments,
)


class ParserExit(Exception):
    """Carry an argparse completion status without terminating the process."""

    def __init__(self, status: int) -> None:
        """Create a parser completion signal."""
        super().__init__(status)
        self.status = status


class _CliArgumentParser(argparse.ArgumentParser):
    def __init__(
        self,
        *args: object,
        stdout: TextIO,
        stderr: TextIO,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._stdout = stdout
        self._stderr = stderr

    def print_help(self, file: TextIO | None = None) -> None:
        super().print_help(self._stdout if file is None else file)

    def print_usage(self, file: TextIO | None = None) -> None:
        super().print_usage(self._stderr if file is None else file)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if message is not None:
            stream = self._stdout if status == 0 else self._stderr
            _write(stream, message)
        raise ParserExit(status)

    def error(self, message: str) -> None:
        self.print_usage(self._stderr)
        _write(self._stderr, f"{self.prog}: error: {message}\n")
        raise ParserExit(2)


def parse_arguments(
    argv: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
) -> CliArguments:
    """Parse process arguments into one immutable command value."""
    parser = _create_parser(stdout, stderr)
    namespace = parser.parse_args(argv)
    if namespace.command == "version":
        return VersionArguments()
    sync_arguments = SyncArguments(
        product_urls=tuple(namespace.product_urls),
        state_file=namespace.state_file,
        timeout_seconds=namespace.timeout_seconds,
        price_drop_percentage=namespace.price_drop_percentage,
        price_drop_amount=namespace.price_drop_amount,
    )
    if namespace.command == "watch":
        return WatchArguments(
            sync=sync_arguments,
            interval=timedelta(seconds=namespace.interval_seconds),
            max_cycles=namespace.max_cycles,
        )
    return sync_arguments


def _create_parser(stdout: TextIO, stderr: TextIO) -> _CliArgumentParser:
    parser = _CliArgumentParser(
        prog="price-watch",
        description="Monitor product prices and availability.",
        allow_abbrev=False,
        stdout=stdout,
        stderr=stderr,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "version",
        help="show the Price Watch version",
        allow_abbrev=False,
        stdout=stdout,
        stderr=stderr,
    )
    sync_parser = subparsers.add_parser(
        "sync",
        help="run one synchronization cycle",
        allow_abbrev=False,
        stdout=stdout,
        stderr=stderr,
    )
    _add_sync_arguments(sync_parser)
    watch_parser = subparsers.add_parser(
        "watch",
        help="run synchronization repeatedly",
        allow_abbrev=False,
        stdout=stdout,
        stderr=stderr,
    )
    _add_sync_arguments(watch_parser)
    watch_parser.add_argument(
        "--interval-seconds",
        required=True,
        type=_positive_integer,
        metavar="INTEGER",
    )
    watch_parser.add_argument(
        "--max-cycles",
        type=_positive_integer,
        default=None,
        metavar="INTEGER",
    )
    return parser


def _add_sync_arguments(parser: _CliArgumentParser) -> None:
    parser.add_argument(
        "--url",
        dest="product_urls",
        action="append",
        required=True,
        metavar="HTTPS_LIDL_PRODUCT_URL",
    )
    parser.add_argument(
        "--state-file",
        required=True,
        type=Path,
        metavar="PATH",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_integer,
        default=10,
        metavar="INTEGER",
    )
    parser.add_argument(
        "--price-drop-percentage",
        type=_percentage,
        default=None,
        metavar="DECIMAL",
    )
    parser.add_argument(
        "--price-drop-amount",
        type=_non_negative_decimal,
        default=None,
        metavar="DECIMAL",
    )


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _percentage(value: str) -> Decimal:
    parsed = _decimal(value)
    if parsed < Decimal("0") or parsed > Decimal("100"):
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return parsed


def _non_negative_decimal(value: str) -> Decimal:
    parsed = _decimal(value)
    if parsed < Decimal("0"):
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("must be a decimal number") from error
    if not parsed.is_finite():
        raise argparse.ArgumentTypeError("must be finite")
    return parsed


def _write(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()
