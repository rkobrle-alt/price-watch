"""UTF-8 JSON configuration loader."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from core.configuration import ConfigurationError


class JsonConfigurationLoader:
    """Load a JSON object without application-schema interpretation."""

    def load(self, path: Path) -> Mapping[str, object]:
        """Read and decode one explicit UTF-8 JSON document."""
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        try:
            content = path.read_text(encoding="utf-8")
            document = json.loads(content)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfigurationError(
                f"failed to load JSON configuration: {path}"
            ) from error
        if not isinstance(document, Mapping):
            raise ConfigurationError("JSON configuration root must be an object")
        return cast(Mapping[str, object], document)
