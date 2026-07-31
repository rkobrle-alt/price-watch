"""Public application configuration contracts for Core."""

from core.configuration.contract import ConfigurationLoader
from core.configuration.exceptions import ConfigurationError

__all__ = ["ConfigurationError", "ConfigurationLoader"]
