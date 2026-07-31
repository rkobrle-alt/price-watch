"""Public API for the Price Watch command-line application."""

from applications.cli.main import main, run
from applications.cli.version import VERSION

__all__ = ["VERSION", "main", "run"]
