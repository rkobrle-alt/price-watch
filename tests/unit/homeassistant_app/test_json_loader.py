"""Tests for the JSON configuration loader."""

from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigurationError, ConfigurationLoader
from infrastructure.configuration.json import JsonConfigurationLoader


def test_json_loader_reads_utf8_object_and_implements_protocol(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text('{"name": "Parkside"}', encoding="utf-8")
    loader = JsonConfigurationLoader()

    assert loader.load(path) == {"name": "Parkside"}
    assert isinstance(loader, ConfigurationLoader)


def test_json_loader_rejects_invalid_path_type() -> None:
    with pytest.raises(TypeError, match="path"):
        JsonConfigurationLoader().load(cast(Path, "options.json"))


@pytest.mark.parametrize("content", [b"\xff", b'{"broken": }'])
def test_json_loader_translates_decode_failures(
    tmp_path: Path,
    content: bytes,
) -> None:
    path = tmp_path / "options.json"
    path.write_bytes(content)

    with pytest.raises(ConfigurationError) as captured:
        JsonConfigurationLoader().load(path)

    assert captured.value.__cause__ is not None
    assert str(path) in str(captured.value)


def test_json_loader_translates_filesystem_failure(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    with pytest.raises(ConfigurationError) as captured:
        JsonConfigurationLoader().load(path)

    assert isinstance(captured.value.__cause__, OSError)


def test_json_loader_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="root must be an object") as captured:
        JsonConfigurationLoader().load(path)

    assert captured.value.__cause__ is None


def test_json_loader_propagates_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    failure = RuntimeError("bug")

    def fail_read(path: Path, *, encoding: str) -> str:
        raise failure

    monkeypatch.setattr(Path, "read_text", fail_read)

    with pytest.raises(RuntimeError) as captured:
        JsonConfigurationLoader().load(tmp_path / "options.json")

    assert captured.value is failure
