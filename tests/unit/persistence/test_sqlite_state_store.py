"""Behavior tests for SQLite latest state and observation history."""

import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest

from core.domain import ProductId
from core.state import (
    LatestSnapshotReader,
    ObservationHistory,
    ObservationStatisticsReader,
    StateStore,
    StateStoreError,
)
from infrastructure.persistence.sqlite import SqliteStateStore
from infrastructure.persistence.sqlite.database import (
    SqliteDatabase,
    SqlitePersistenceError,
)
from infrastructure.persistence.sqlite.state_store import (
    _reclaimable_database_bytes,
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


def _as_latest_reader(store: LatestSnapshotReader) -> LatestSnapshotReader:
    return store


def _as_statistics_reader(
    store: ObservationStatisticsReader,
) -> ObservationStatisticsReader:
    return store


def test_constructor_has_no_io_and_implements_both_protocols(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing" / "state.sqlite3"
    store = SqliteStateStore(path)

    assert _as_state_store(store) is store
    assert _as_history(store) is store
    assert _as_latest_reader(store) is store
    assert _as_statistics_reader(store) is store
    assert not path.parent.exists()


def test_missing_database_and_unknown_product_return_none_and_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SqliteStateStore(path)

    assert store.load(PRODUCT_ID) is None
    assert store.history(PRODUCT_ID) == ()
    assert store.latest_snapshots() == ()
    statistics = store.observation_statistics()
    assert statistics.observation_count == 0
    assert statistics.observed_product_count == 0
    assert statistics.first_observation_at is None
    assert statistics.last_observation_at is None
    assert statistics.storage_size_bytes > 0
    assert statistics.reclaimable_size_bytes == 0
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


def test_statistics_use_insertion_boundaries_and_preserve_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SqliteStateStore(path)
    first = create_snapshot(timestamp=SNAPSHOT_TIME)
    other = create_snapshot(
        product_id=OTHER_PRODUCT_ID,
        timestamp=SNAPSHOT_TIME + timedelta(days=1),
    )
    last = create_snapshot(timestamp=SNAPSHOT_TIME - timedelta(days=1))
    for snapshot in (first, other, last):
        store.save(snapshot)

    statistics = store.observation_statistics()

    assert statistics.observation_count == 3
    assert statistics.observed_product_count == 2
    assert statistics.first_observation_at == first.timestamp
    assert statistics.last_observation_at == last.timestamp
    with open_database(path) as connection:
        page_count = connection.execute("PRAGMA page_count").fetchone()[0]
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        assert connection.execute("PRAGMA user_version").fetchone() == (4,)
        assert connection.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone() == (3,)
    assert statistics.storage_size_bytes == page_count * page_size
    assert statistics.reclaimable_size_bytes == 0


def test_products_have_independent_histories(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "state.sqlite3")
    first = create_snapshot(amount="100")
    other = create_snapshot(product_id=OTHER_PRODUCT_ID, amount="300")
    store.save(first)
    store.save(other)

    assert store.history(PRODUCT_ID) == (first,)
    assert store.history(OTHER_PRODUCT_ID) == (other,)


def test_latest_snapshots_returns_last_value_per_product_in_id_order(
    tmp_path: Path,
) -> None:
    store = SqliteStateStore(tmp_path / "state.sqlite3")
    first = create_snapshot(amount="100")
    latest = create_snapshot(amount="80")
    other = create_snapshot(product_id=OTHER_PRODUCT_ID, amount="300")
    store.save(other)
    store.save(first)
    store.save(latest)

    assert store.latest_snapshots() == (latest, other)


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
@pytest.mark.parametrize(
    "method",
    ["load", "history", "latest_snapshots", "observation_statistics"],
)
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
        if method == "latest_snapshots":
            store.latest_snapshots()
        elif method == "observation_statistics":
            store.observation_statistics()
        else:
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

    with pytest.raises(StateStoreError):
        store.latest_snapshots()


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


@pytest.mark.parametrize("operation", ["save", "history", "latest", "statistics"])
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
        elif operation == "history":
            store.history(PRODUCT_ID)
        elif operation == "latest":
            store.latest_snapshots()
        else:
            store.observation_statistics()

    assert captured.value.__cause__ is not None


@pytest.mark.parametrize(
    ("page_count", "page_size"),
    [(True, 4096), ("1", 4096), (1, True), (1, "4096"), (-1, 4096), (1, 0)],
)
def test_statistics_wrap_invalid_sqlite_page_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    page_count: object,
    page_size: object,
) -> None:
    class _Result:
        def __init__(self, row: tuple[object, ...]) -> None:
            self._row = row

        def fetchone(self) -> tuple[object, ...]:
            return self._row

    class _Connection:
        def execute(
            self,
            statement: str,
            parameters: tuple[object, ...] = (),
        ) -> _Result:
            if statement.startswith("SELECT COUNT"):
                return _Result((0, 0, None, None))
            if statement == "PRAGMA page_count":
                return _Result((page_count,))
            return _Result((page_size,))

    connection = _Connection()
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: connection)
    monkeypatch.setattr(SqliteDatabase, "close", lambda database, value: None)

    with pytest.raises(StateStoreError, match="invalid persisted") as captured:
        SqliteStateStore(tmp_path / "state.sqlite3").observation_statistics()

    assert captured.value.__cause__ is not None


def test_statistics_wrap_query_failure_after_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = sqlite3.OperationalError("query failed")

    class _Connection:
        def execute(self, statement: str) -> None:
            raise failure

    connection = _Connection()
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: connection)
    monkeypatch.setattr(SqliteDatabase, "close", lambda database, value: None)

    with pytest.raises(StateStoreError, match="failed to read") as captured:
        SqliteStateStore(tmp_path / "state.sqlite3").observation_statistics()

    assert captured.value.__cause__ is failure


@pytest.mark.parametrize(
    ("free_page_count", "page_size"),
    [
        (True, 4096),
        ("1", 4096),
        (1, True),
        (1, "4096"),
        (-1, 4096),
        (1, 0),
    ],
)
def test_statistics_wrap_invalid_sqlite_free_page_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    free_page_count: object,
    page_size: object,
) -> None:
    class _Result:
        def __init__(self, row: tuple[object, ...]) -> None:
            self._row = row

        def fetchone(self) -> tuple[object, ...]:
            return self._row

    class _Connection:
        def execute(
            self,
            statement: str,
            parameters: tuple[object, ...] = (),
        ) -> _Result:
            if statement.startswith("SELECT COUNT"):
                return _Result((0, 0, None, None))
            if statement == "PRAGMA page_count":
                return _Result((10,))
            if statement == "PRAGMA freelist_count":
                return _Result((free_page_count,))
            return _Result((page_size,))

    connection = _Connection()
    monkeypatch.setattr(SqliteDatabase, "open", lambda database: connection)
    monkeypatch.setattr(SqliteDatabase, "close", lambda database, value: None)

    with pytest.raises(StateStoreError, match="invalid persisted") as captured:
        SqliteStateStore(tmp_path / "state.sqlite3").observation_statistics()

    assert captured.value.__cause__ is not None


@pytest.mark.parametrize("page_size", [True, "4096"])
def test_reclaimable_bytes_reject_invalid_page_size(page_size: object) -> None:
    class _Result:
        def __init__(self, value: object) -> None:
            self._value = value

        def fetchone(self) -> tuple[object]:
            return (self._value,)

    class _Connection:
        def execute(self, statement: str) -> _Result:
            return _Result(1 if statement == "PRAGMA freelist_count" else page_size)

    with pytest.raises(TypeError, match="page size"):
        _reclaimable_database_bytes(cast(sqlite3.Connection, _Connection()))

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
