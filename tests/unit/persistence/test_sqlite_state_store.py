"""Behavior tests for SQLite latest state and observation history."""

import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from core.domain import ProductId
from core.state import ObservationHistory, StateStore, StateStoreError
from infrastructure.persistence.sqlite import SqliteStateStore
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
)
from tests.unit.persistence.helpers import (
    OTHER_PRODUCT_ID,
    PRODUCT_ID,
    SNAPSHOT_TIME,
    create_snapshot,
)
from tests.unit.persistence.sqlite_helpers import open_database


def _as_state_store(store: StateStore) -> StateStore:
    return store


def _as_history(store: ObservationHistory) -> ObservationHistory:
    return store


def test_constructor_has_no_io_and_implements_both_protocols(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing" / "state.sqlite3"
    store = SqliteStateStore(path)

    assert _as_state_store(store) is store
    assert _as_history(store) is store
    assert not path.parent.exists()


def test_missing_database_and_unknown_product_return_none_and_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SqliteStateStore(path)

    assert store.load(PRODUCT_ID) is None
    assert store.history(PRODUCT_ID) == ()
    assert path.exists()


def test_snapshot_round_trips_exactly_through_reopened_store(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    snapshot = create_snapshot()

    SqliteStateStore(path).save(snapshot)
    loaded = SqliteStateStore(path).load(PRODUCT_ID)

    assert loaded == snapshot
    assert loaded is not snapshot
    assert loaded.product is not snapshot.product


def test_nullable_values_round_trip(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "state.sqlite3")
    snapshot = create_snapshot(
        original_price=None,
        image_url=None,
        availability=True,
    )

    store.save(snapshot)

    assert store.load(PRODUCT_ID) == snapshot


def test_every_save_is_retained_and_load_is_last_write_wins(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "state.sqlite3")
    first = create_snapshot(amount="100", timestamp=SNAPSHOT_TIME)
    duplicate = create_snapshot(amount="100", timestamp=SNAPSHOT_TIME)
    older_timestamp = create_snapshot(
        amount="80",
        timestamp=SNAPSHOT_TIME - timedelta(days=1),
    )

    store.save(first)
    store.save(duplicate)
    store.save(older_timestamp)

    assert store.history(PRODUCT_ID) == (first, duplicate, older_timestamp)
    assert store.load(PRODUCT_ID) == older_timestamp


def test_products_have_independent_histories(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "state.sqlite3")
    first = create_snapshot(amount="100")
    other = create_snapshot(product_id=OTHER_PRODUCT_ID, amount="300")
    store.save(first)
    store.save(other)

    assert store.history(PRODUCT_ID) == (first,)
    assert store.history(OTHER_PRODUCT_ID) == (other,)


@pytest.mark.parametrize(
    ("limit", "expected_amounts"),
    [
        (None, ["100", "90", "80"]),
        (1, ["80"]),
        (2, ["90", "80"]),
        (10, ["100", "90", "80"]),
    ],
)
def test_history_limit_returns_newest_values_in_chronological_order(
    tmp_path: Path,
    limit: int | None,
    expected_amounts: list[str],
) -> None:
    store = SqliteStateStore(tmp_path / "state.sqlite3")
    for amount in ("100", "90", "80"):
        store.save(create_snapshot(amount=amount))

    snapshots = store.history(PRODUCT_ID, limit)

    assert [str(snapshot.product.current_price.amount) for snapshot in snapshots] == (
        expected_amounts
    )


def test_raw_observation_json_preserves_exact_decimal_strings(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    SqliteStateStore(path).save(create_snapshot())

    with open_database(path) as connection:
        payload = connection.execute(
            "SELECT snapshot FROM observations"
        ).fetchone()[0]
    decoded = json.loads(payload)
    product = decoded["product"]
    assert product["current_price"]["amount"] == "199.9900"
    assert product["original_price"]["amount"] == "249.9900"
    assert product["discount_percent"] == "20.0040"
    assert isinstance(product["current_price"]["amount"], str)


@pytest.mark.parametrize("method", ["load", "history"])
def test_read_methods_reject_invalid_product_id_before_io(
    tmp_path: Path,
    method: str,
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SqliteStateStore(path)

    with pytest.raises(TypeError, match="product_id"):
        getattr(store, method)("invalid")
    assert not path.exists()


def test_save_rejects_invalid_snapshot_before_io(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"

    with pytest.raises(TypeError, match="snapshot"):
        SqliteStateStore(path).save("invalid")  # type: ignore[arg-type]
    assert not path.exists()


@pytest.mark.parametrize("limit", [True, 1.5, "1"])
def test_history_rejects_invalid_limit_type_before_io(
    tmp_path: Path,
    limit: object,
) -> None:
    path = tmp_path / "state.sqlite3"

    with pytest.raises(TypeError, match="limit"):
        SqliteStateStore(path).history(  # type: ignore[arg-type]
            PRODUCT_ID,
            limit,
        )
    assert not path.exists()


@pytest.mark.parametrize("limit", [0, -1])
def test_history_rejects_non_positive_limit_before_io(
    tmp_path: Path,
    limit: int,
) -> None:
    path = tmp_path / "state.sqlite3"

    with pytest.raises(ValueError, match="limit"):
        SqliteStateStore(path).history(PRODUCT_ID, limit)
    assert not path.exists()


@pytest.mark.parametrize("payload", ["{broken", "[]"])
@pytest.mark.parametrize("method", ["load", "history"])
def test_read_wraps_invalid_snapshot_payload(
    tmp_path: Path,
    payload: str,
    method: str,
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SqliteStateStore(path)
    store.save(create_snapshot())
    with open_database(path) as connection:
        connection.execute(
            "UPDATE observations SET snapshot = ?",
            (payload,),
        )
        connection.commit()

    with pytest.raises(StateStoreError, match="invalid persisted") as captured:
        getattr(store, method)(PRODUCT_ID)

    assert captured.value.__cause__ is not None


def test_read_wraps_indexed_product_id_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SqliteStateStore(path)
    store.save(create_snapshot())
    with open_database(path) as connection:
        connection.execute(
            "UPDATE observations SET product_id = ?",
            (str(OTHER_PRODUCT_ID.value),),
        )
        connection.commit()

    with pytest.raises(StateStoreError) as captured:
        store.load(OTHER_PRODUCT_ID)

    assert captured.value.__cause__ is not None


def test_non_string_snapshot_value_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SqliteStateStore(path)
    store.save(create_snapshot())
    with open_database(path) as connection:
        connection.execute(
            "UPDATE observations SET snapshot = ?",
            (sqlite3.Binary(b"binary"),),
        )
        connection.commit()

    with pytest.raises(StateStoreError) as captured:
        store.history(PRODUCT_ID)

    assert captured.value.__cause__ is not None


@pytest.mark.parametrize("operation", ["save", "history"])
def test_additional_operations_wrap_connect_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    failure = sqlite3.OperationalError("cannot open")

    def fail_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise failure

    monkeypatch.setattr(
        "infrastructure.persistence.sqlite.database.sqlite3.connect",
        fail_connect,
    )
    store = SqliteStateStore(tmp_path / "state.sqlite3")

    with pytest.raises(StateStoreError) as captured:
        if operation == "save":
            store.save(create_snapshot())
        else:
            store.history(PRODUCT_ID)

    assert captured.value.__cause__ is not None

def test_save_handles_database_failure_before_connection_assignment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = SqlitePersistenceError("open failed")

    def fail_open(database: SqliteDatabase) -> sqlite3.Connection:
        raise failure

    monkeypatch.setattr(SqliteDatabase, "open", fail_open)

    with pytest.raises(StateStoreError) as captured:
        SqliteStateStore(tmp_path / "state.sqlite3").save(create_snapshot())

    assert captured.value.__cause__ is failure

def test_save_wraps_insert_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = sqlite3.OperationalError("insert failed")

    class FailingConnection:
        def __enter__(self) -> "FailingConnection":
            return self

        def __exit__(
            self,
            exception_type: type[BaseException] | None,
            exception: BaseException | None,
            traceback: object | None,
        ) -> None:
            return None

        def execute(
            self,
            statement: str,
            parameters: tuple[str, str],
        ) -> None:
            raise failure

    connection = FailingConnection()
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: connection)
    monkeypatch.setattr(SqliteDatabase, "close", lambda database, value: None)

    with pytest.raises(StateStoreError) as captured:
        SqliteStateStore(tmp_path / "state.sqlite3").save(create_snapshot())

    assert captured.value.__cause__ is failure
