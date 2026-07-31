"""Tests for the Infrastructure TOML loader."""

from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigurationError, ConfigurationLoader
from infrastructure.configuration.toml import TomlConfigurationLoader


def test_loader_reads_utf8_toml_and_implements_protocol(tmp_path: Path) -> None:
    path = tmp_path / "price-watch.toml"
    path.write_text('schema_version = 1\nname = "Příliš žluťoučký"\n', encoding="utf-8")
    loader = TomlConfigurationLoader()

    document = loader.load(path)

    assert isinstance(loader, ConfigurationLoader)
    assert document == {"schema_version": 1, "name": "Příliš žluťoučký"}


def test_loader_rejects_invalid_path_type() -> None:
    with pytest.raises(TypeError):
        TomlConfigurationLoader().load(cast(Path, "config.toml"))


@pytest.mark.parametrize("content", [b"\xff", b"invalid = ["])
def test_loader_translates_decode_failures(
    tmp_path: Path,
    content: bytes,
) -> None:
    path = tmp_path / "invalid.toml"
    path.write_bytes(content)

    with pytest.raises(ConfigurationError) as captured:
        TomlConfigurationLoader().load(path)

    assert captured.value.__cause__ is not None
    assert str(path) in str(captured.value)


def test_loader_translates_filesystem_failure(tmp_path: Path) -> None:
    path = tmp_path / "missing.toml"

    with pytest.raises(ConfigurationError) as captured:
        TomlConfigurationLoader().load(path)

    assert isinstance(captured.value.__cause__, OSError)


def test_loader_propagates_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    failure = RuntimeError("bug")

    def fail(path: Path) -> bytes:
        raise failure

    monkeypatch.setattr(Path, "read_bytes", fail)

    with pytest.raises(RuntimeError) as captured:
        TomlConfigurationLoader().load(tmp_path / "config.toml")

    assert captured.value is failure
