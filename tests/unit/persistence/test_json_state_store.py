"""Behavior and filesystem-failure tests for JsonStateStore."""

import json
from pathlib import Path
from typing import cast

import pytest

from core.domain import ProductId
from core.state import StateSnapshot, StateStore, StateStoreError
from infrastructure.persistence.json import JsonStateStore
from tests.unit.persistence.helpers import (
    OTHER_PRODUCT_ID,
    PRODUCT_ID,
    create_snapshot,
)


def _as_state_store(store: StateStore) -> StateStore:
    return store


def test_constructor_has_no_filesystem_side_effect_and_implements_protocol(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "missing" / "state.json"
    store = JsonStateStore(destination)

    assert _as_state_store(store) is store
    assert not destination.parent.exists()


def test_constructor_rejects_invalid_path_type() -> None:
    with pytest.raises(TypeError, match="path must be a Path"):
        JsonStateStore("state.json")  # type: ignore[arg-type]


def test_missing_file_and_unknown_product_return_none(tmp_path: Path) -> None:
    destination = tmp_path / "state.json"
    store = JsonStateStore(destination)

    assert store.load(PRODUCT_ID) is None

    store.save(create_snapshot())

    assert store.load(OTHER_PRODUCT_ID) is None


def test_methods_reject_invalid_public_argument_types(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "state.json")

    with pytest.raises(TypeError, match="ProductId"):
        store.load("id")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="StateSnapshot"):
        store.save("snapshot")  # type: ignore[arg-type]


def test_full_snapshot_round_trips_through_new_store_instance(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "state.json"
    snapshot = create_snapshot()

    JsonStateStore(destination).save(snapshot)
    loaded = JsonStateStore(destination).load(snapshot.product.id)

    assert loaded == snapshot
    assert loaded is not snapshot
    assert loaded.product is not snapshot.product
    assert destination.parent.is_dir()


def test_nullable_fields_and_in_stock_value_round_trip(tmp_path: Path) -> None:
    destination = tmp_path / "state.json"
    snapshot = create_snapshot(
        original_price=None,
        image_url=None,
        availability=True,
    )

    JsonStateStore(destination).save(snapshot)

    assert JsonStateStore(destination).load(PRODUCT_ID) == snapshot


def test_output_is_deterministic_schema_v1_json(tmp_path: Path) -> None:
    destination = tmp_path / "state.json"
    snapshot = create_snapshot()

    JsonStateStore(destination).save(snapshot)

    content = destination.read_text(encoding="utf-8")
    decoded = json.loads(content)
    expected = json.dumps(
        decoded,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    product = decoded["snapshots"][str(PRODUCT_ID.value)]["product"]
    assert content == expected
    assert content.endswith("\n") and not content.endswith("\n\n")
    assert decoded["schema_version"] == 1
    assert product["current_price"]["amount"] == "199.9900"
    assert product["original_price"]["amount"] == "249.9900"
    assert product["discount_percent"] == "20.0040"
    assert isinstance(product["current_price"]["amount"], str)


def test_last_write_wins_and_preserves_other_products(tmp_path: Path) -> None:
    destination = tmp_path / "state.json"
    store = JsonStateStore(destination)
    first = create_snapshot(amount="100")
    other = create_snapshot(product_id=OTHER_PRODUCT_ID, amount="300")
    replacement = create_snapshot(amount="90")

    store.save(first)
    store.save(other)
    store.save(replacement)

    assert store.load(PRODUCT_ID) == replacement
    assert store.load(OTHER_PRODUCT_ID) == other


def test_store_reads_file_on_every_load_without_cache(tmp_path: Path) -> None:
    destination = tmp_path / "state.json"
    first_store = JsonStateStore(destination)
    first_store.save(create_snapshot(amount="100"))

    replacement = create_snapshot(amount="80")
    JsonStateStore(destination).save(replacement)

    assert first_store.load(PRODUCT_ID) == replacement


def test_read_os_error_is_wrapped_with_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = OSError("read failed")

    def fail_read(path: Path, *, encoding: str) -> str:
        raise failure

    monkeypatch.setattr(Path, "read_text", fail_read)

    with pytest.raises(StateStoreError, match="failed to read") as captured:
        JsonStateStore(tmp_path / "state.json").load(PRODUCT_ID)

    assert captured.value.__cause__ is failure


def test_invalid_utf8_is_wrapped_with_cause(tmp_path: Path) -> None:
    destination = tmp_path / "state.json"
    destination.write_bytes(b"\xff")

    with pytest.raises(StateStoreError, match="failed to read") as captured:
        JsonStateStore(destination).load(PRODUCT_ID)

    assert isinstance(captured.value.__cause__, UnicodeDecodeError)


def test_malformed_json_is_wrapped_with_cause(tmp_path: Path) -> None:
    destination = tmp_path / "state.json"
    destination.write_text("{broken", encoding="utf-8")

    with pytest.raises(StateStoreError, match="invalid state") as captured:
        JsonStateStore(destination).load(PRODUCT_ID)

    assert isinstance(captured.value.__cause__, json.JSONDecodeError)


def test_parent_directory_failure_is_wrapped_without_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = OSError("mkdir failed")

    def fail_mkdir(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        raise failure

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    with pytest.raises(StateStoreError, match="failed to write") as captured:
        JsonStateStore(tmp_path / "missing" / "state.json").save(create_snapshot())

    assert captured.value.__cause__ is failure


def test_temporary_file_creation_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = OSError("temporary file failed")

    def fail_temporary_file(**kwargs: object) -> object:
        raise failure

    monkeypatch.setattr(
        "infrastructure.persistence.json.store.NamedTemporaryFile",
        fail_temporary_file,
    )

    with pytest.raises(StateStoreError) as captured:
        JsonStateStore(tmp_path / "state.json").save(create_snapshot())

    assert captured.value.__cause__ is failure


@pytest.mark.parametrize("stage", ["write", "flush"])
def test_temporary_write_and_flush_failures_are_wrapped_and_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    destination = tmp_path / "state.json"
    state_store = JsonStateStore(destination)
    failure = OSError(f"{stage} failed")
    temporary_path = tmp_path / f".{destination.name}.test.tmp"

    class FailingTemporaryFile:
        name = str(temporary_path)

        def __enter__(self) -> "FailingTemporaryFile":
            temporary_path.write_text("partial", encoding="utf-8")
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def write(self, content: str) -> int:
            if stage == "write":
                raise failure
            return len(content)

        def flush(self) -> None:
            if stage == "flush":
                raise failure

        def fileno(self) -> int:
            return 1

    monkeypatch.setattr(
        "infrastructure.persistence.json.store.NamedTemporaryFile",
        lambda **kwargs: FailingTemporaryFile(),
    )

    with pytest.raises(StateStoreError) as captured:
        state_store.save(create_snapshot(amount="90"))

    assert captured.value.__cause__ is failure
    assert not temporary_path.exists()


def test_fsync_failure_is_wrapped_and_temporary_file_is_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = OSError("fsync failed")

    def fail_fsync(file_descriptor: int) -> None:
        raise failure

    monkeypatch.setattr("infrastructure.persistence.json.store.fsync", fail_fsync)
    destination = tmp_path / "state.json"
    state_store = JsonStateStore(destination)

    with pytest.raises(StateStoreError) as captured:
        state_store.save(create_snapshot(amount="90"))

    assert captured.value.__cause__ is failure
    assert list(tmp_path.glob("*.tmp")) == []


def test_replace_failure_preserves_destination_and_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "state.json"
    state_store = JsonStateStore(destination)
    state_store.save(create_snapshot(amount="100"))
    original = destination.read_bytes()
    failure = OSError("replace failed")

    def fail_replace(source: Path, target: Path) -> None:
        raise failure

    monkeypatch.setattr("infrastructure.persistence.json.store.replace", fail_replace)

    with pytest.raises(StateStoreError) as captured:
        state_store.save(create_snapshot(amount="90"))

    assert captured.value.__cause__ is failure
    assert destination.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_cleanup_failure_does_not_replace_original_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "state.json"
    state_store = JsonStateStore(destination)
    failure = OSError("replace failed")

    monkeypatch.setattr(
        "infrastructure.persistence.json.store.replace",
        lambda source, target: (_ for _ in ()).throw(failure),
    )
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda path, *, missing_ok=False: (_ for _ in ()).throw(
            OSError("cleanup failed")
        ),
    )

    with pytest.raises(StateStoreError) as captured:
        state_store.save(create_snapshot(amount="90"))

    assert captured.value.__cause__ is failure
