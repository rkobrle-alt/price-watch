"""Immutable migration archive values and errors."""

from dataclasses import dataclass
from pathlib import Path

STATE_FILE_NAMES = ("catalog.sqlite3", "state.json")


class MigrationArchiveError(RuntimeError):
    """Report migration archive, integrity or persistence failures."""


@dataclass(frozen=True, slots=True)
class MigrationExportResult:
    """Identify one completed migration export and its state payload."""

    archive_file: Path
    archive_sha256: str
    state_file_name: str

    def __post_init__(self) -> None:
        """Validate the completed export description."""
        if not isinstance(self.archive_file, Path):
            raise TypeError("archive_file must be a Path")
        if not isinstance(self.archive_sha256, str):
            raise TypeError("archive_sha256 must be a string")
        if len(self.archive_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.archive_sha256
        ):
            raise ValueError("archive_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.state_file_name, str):
            raise TypeError("state_file_name must be a string")
        if self.state_file_name not in STATE_FILE_NAMES:
            raise ValueError("state_file_name is unsupported")
