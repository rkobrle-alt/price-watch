"""Tests for persistent timestamped retention backup paths."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

from core.state import StateStoreError
from infrastructure.persistence.sqlite import (
    TimestampedRetentionBackupFileFactory,
)


def test_factory_creates_directory_and_utc_timestamped_path(tmp_path: Path) -> None:
    directory = tmp_path / "persistent" / "retention-backups"
    factory = TimestampedRetentionBackupFileFactory(directory)

    path = factory(datetime(2026, 8, 1, 12, 30, 45, 123456, tzinfo=UTC))

    assert directory.is_dir()
    assert path == directory / (
        "catalog-before-retention-20260801T123045.123456Z.sqlite3"
    )
    assert not path.exists()


def test_factory_normalizes_timestamp_and_rejects_collision(tmp_path: Path) -> None:
    factory = TimestampedRetentionBackupFileFactory(tmp_path)
    offset = timezone(timedelta(hours=2))
    timestamp = datetime(2026, 8, 1, 14, 30, 45, tzinfo=offset)
    path = factory(timestamp)
    path.write_bytes(b"existing")

    with pytest.raises(StateStoreError, match="prepare") as captured:
        factory(timestamp)

    assert path.name == "catalog-before-retention-20260801T123045.000000Z.sqlite3"
    assert isinstance(captured.value.__cause__, FileExistsError)
    assert offset.utcoffset(None) == timedelta(hours=2)


def test_factory_wraps_directory_creation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = OSError("read only")
    monkeypatch.setattr(
        Path,
        "mkdir",
        lambda *arguments, **keywords: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(StateStoreError, match="prepare") as captured:
        TimestampedRetentionBackupFileFactory(tmp_path / "x")(
            datetime(2026, 8, 1, tzinfo=UTC)
        )

    assert captured.value.__cause__ is failure


@pytest.mark.parametrize(
    ("factory_argument", "timestamp", "exception_type", "message"),
    [
        ("directory", datetime(2026, 8, 1, tzinfo=UTC), TypeError, "directory"),
        (Path("backup"), cast(datetime, "now"), TypeError, "timestamp"),
        (Path("backup"), datetime(2026, 8, 1), ValueError, "timezone-aware"),
    ],
)
def test_factory_rejects_invalid_arguments(
    factory_argument: object,
    timestamp: datetime,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        factory = TimestampedRetentionBackupFileFactory(
            cast(Path, factory_argument)
        )
        factory(timestamp)
