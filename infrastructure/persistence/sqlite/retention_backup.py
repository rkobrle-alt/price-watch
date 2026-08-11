"""Prepare persistent timestamped files for retention backups."""

from datetime import UTC, datetime
from pathlib import Path

from core.state import StateStoreError


class TimestampedRetentionBackupFileFactory:
    """Create a backup directory and return one collision-safe file path."""

    def __init__(self, directory: Path) -> None:
        """Configure the explicit persistent backup directory."""
        if not isinstance(directory, Path):
            raise TypeError("directory must be a Path")
        self._directory = directory

    def __call__(self, timestamp: datetime) -> Path:
        """Prepare the directory and return a new UTC-timestamped path."""
        _validate_timestamp(timestamp)
        name = (
            "catalog-before-retention-"
            f"{timestamp.astimezone(UTC):%Y%m%dT%H%M%S.%fZ}.sqlite3"
        )
        path = self._directory / name
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise FileExistsError(f"backup file already exists: {path}")
        except OSError as error:
            raise StateStoreError(
                f"failed to prepare retention backup file: {path}"
            ) from error
        return path


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
