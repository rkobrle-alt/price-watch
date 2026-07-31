"""Public API for pure application configuration."""

from applications.configuration.model import ApplicationConfig
from applications.configuration.parser import parse_configuration

__all__ = ["ApplicationConfig", "parse_configuration"]
