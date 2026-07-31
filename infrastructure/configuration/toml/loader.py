"""UTF-8 TOML configuration file loader."""

import tomllib
from collections.abc import Mapping
from pathlib import Path

from core.configuration import ConfigurationError


class TomlConfigurationLoader:
    """Load a neutral TOML document from an explicit filesystem path."""

    def load(self, path: Path) -> Mapping[str, object]:
        """Read and decode one UTF-8 TOML document."""
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        try:
            text = path.read_bytes().decode("utf-8")
            return tomllib.loads(text)
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise ConfigurationError(
                f"cannot load configuration {path}: {error}"
            ) from error
