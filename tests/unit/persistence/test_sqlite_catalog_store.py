"""Behavior tests for SQLite catalog membership persistence."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.catalog import (
    CatalogStatistics,
    CatalogStatisticsReader,
    CatalogStore,
    CatalogStoreError,
    ProductReference,
)
from infrastructure.persistence.sqlite import SqliteCatalogStore
from tests.unit.persistence.sqlite_helpers import (
    CATALOG_PROVIDER_ID,
    OTHER_PROVIDER_ID,
    create_reference,
    open_database,
)

_FIRST = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
_LATER = _FIRST + timedelta(hours=1)


def _as_catalog_store(store: CatalogStore) -> CatalogStore:
    return store


def test_constructor_has_no_io_and_implements_protocol(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "catalog.sqlite3"
    store = SqliteCatalogStore(path)

    assert _as_catalog_store(store) is store
    assert not path.parent.exists()


def test_empty_discovery_initializes_schema_and_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"

    assert SqliteCatalogStore(path).record_discovery((), _FIRST) == ()
    with open_database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "catalog_entries",
        "notification_reservations",
        "observations",
    }.issubset(tables)


def test_new_and_mixed_provider_references_preserve_input_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    references = (
        create_reference("p1"),
        create_reference("p2", provider_id=OTHER_PROVIDER_ID),
        create_reference("p3"),
    )
    store = SqliteCatalogStore(path)

    assert store.record_discovery(references, _FIRST) == references
    assert [
        entry.reference for entry in store.list_entries(CATALOG_PROVIDER_ID)
    ] == [references[0], references[2]]
    assert store.list_entries(OTHER_PROVIDER_ID)[0].reference == references[1]


def test_repeated_discovery_updates_url_and_last_seen_only(tmp_path: Path) -> None:
    store = SqliteCatalogStore(tmp_path / "catalog.sqlite3")
    first = create_reference("p1", suffix="old")
    changed = create_reference("p1", suffix="new")

    assert store.record_discovery((first,), _FIRST) == (first,)
    assert store.record_discovery((changed,), _LATER) == ()

    entry = store.list_entries(CATALOG_PROVIDER_ID)[0]
    assert entry.reference == changed
    assert entry.first_seen_at == _FIRST
    assert entry.last_seen_at == _LATER


def test_omitted_entries_are_retained_unchanged(tmp_path: Path) -> None:
    store = SqliteCatalogStore(tmp_path / "catalog.sqlite3")
    first = create_reference("p1")
    omitted = create_reference("p2")
    store.record_discovery((first, omitted), _FIRST)

    store.record_discovery((first,), _LATER)

    entries = store.list_entries(CATALOG_PROVIDER_ID)
    assert entries[1].reference == omitted
    assert entries[1].last_seen_at == _FIRST


def test_stale_batch_rolls_back_every_change(tmp_path: Path) -> None:
    store = SqliteCatalogStore(tmp_path / "catalog.sqlite3")
    existing = create_reference("p1")
    store.record_discovery((existing,), _LATER)
    new_reference = create_reference("p2")

    with pytest.raises(ValueError, match="cannot precede"):
        store.record_discovery((new_reference, existing), _FIRST)

    assert [
        entry.reference for entry in store.list_entries(CATALOG_PROVIDER_ID)
    ] == [existing]


def test_reopened_store_reads_durable_entries(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "catalog.sqlite3"
    reference = create_reference("p1")
    SqliteCatalogStore(path).record_discovery((reference,), _FIRST)

    assert SqliteCatalogStore(path).list_entries(CATALOG_PROVIDER_ID)[0].reference == (
        reference
    )


def test_unknown_provider_returns_empty_tuple(tmp_path: Path) -> None:
    store = SqliteCatalogStore(tmp_path / "catalog.sqlite3")
    store.record_discovery((create_reference("p1"),), _FIRST)

    assert store.list_entries(OTHER_PROVIDER_ID) == ()


def test_catalog_statistics_are_durable_and_provider_isolated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    first = create_reference("p1")
    second = create_reference("p2")
    other = create_reference("other", provider_id=OTHER_PROVIDER_ID)
    store.record_discovery((first, second, other), _FIRST)
    store.record_discovery((second,), _LATER)
    store.record_refresh_attempt((first,), _FIRST)
    store.record_refresh_attempt((second,), _LATER)

    reader: CatalogStatisticsReader = SqliteCatalogStore(path)

    assert reader.catalog_statistics(CATALOG_PROVIDER_ID) == CatalogStatistics(
        reference_count=2,
        last_discovered_at=_LATER,
        last_refresh_attempt_at=_LATER,
    )
    assert reader.catalog_statistics(OTHER_PROVIDER_ID) == CatalogStatistics(
        reference_count=1,
        last_discovered_at=_FIRST,
        last_refresh_attempt_at=None,
    )


def test_empty_catalog_statistics_initialize_schema(tmp_path: Path) -> None:
    statistics = SqliteCatalogStore(
        tmp_path / "catalog.sqlite3"
    ).catalog_statistics(CATALOG_PROVIDER_ID)

    assert statistics == CatalogStatistics(0, None, None)


def test_catalog_statistics_validate_provider_before_io(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"

    with pytest.raises(TypeError, match="provider_id"):
        SqliteCatalogStore(path).catalog_statistics("provider")  # type: ignore[arg-type]

    assert not path.exists()


def test_catalog_statistics_wrap_malformed_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    store.record_discovery((create_reference("p1"),), _FIRST)
    with open_database(path) as connection:
        connection.execute("UPDATE catalog_entries SET last_seen_at = 'invalid'")
        connection.commit()

    with pytest.raises(CatalogStoreError, match="invalid persisted") as captured:
        store.catalog_statistics(CATALOG_PROVIDER_ID)

    assert captured.value.__cause__ is not None


def test_catalog_statistics_wrap_database_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SqliteCatalogStore(tmp_path / "catalog.sqlite3")
    failure = sqlite3.OperationalError("query failed")

    def fail_open() -> None:
        raise failure

    monkeypatch.setattr(store._database, "open", fail_open)

    with pytest.raises(CatalogStoreError, match="read catalog statistics") as captured:
        store.catalog_statistics(CATALOG_PROVIDER_ID)

    assert captured.value.__cause__ is failure


@pytest.mark.parametrize("references", [[], (object(),)])
def test_record_rejects_invalid_reference_collection(
    tmp_path: Path,
    references: object,
) -> None:
    path = tmp_path / "catalog.sqlite3"

    with pytest.raises(TypeError, match="references"):
        SqliteCatalogStore(path).record_discovery(  # type: ignore[arg-type]
            references,
            _FIRST,
        )
    assert not path.exists()


def test_record_rejects_duplicate_identity_before_io(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    reference = create_reference("p1")

    with pytest.raises(ValueError, match="unique"):
        SqliteCatalogStore(path).record_discovery(
            (reference, reference),
            _FIRST,
        )
    assert not path.exists()


@pytest.mark.parametrize("timestamp", ["invalid", datetime(2026, 8, 3, 10, 0)])
def test_record_rejects_invalid_timestamp_before_io(
    tmp_path: Path,
    timestamp: object,
) -> None:
    path = tmp_path / "catalog.sqlite3"

    expected = TypeError if isinstance(timestamp, str) else ValueError
    with pytest.raises(expected, match="discovered_at"):
        SqliteCatalogStore(path).record_discovery(  # type: ignore[arg-type]
            (create_reference("p1"),),
            timestamp,
        )
    assert not path.exists()


def test_list_rejects_invalid_provider_type_before_io(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"

    with pytest.raises(TypeError, match="provider_id"):
        SqliteCatalogStore(path).list_entries("provider")  # type: ignore[arg-type]
    assert not path.exists()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("provider_id", "invalid"),
        ("provider_id", b"not-text"),
        ("provider_id", str(CATALOG_PROVIDER_ID.value).upper()),
        ("external_id", " "),
        ("url", " "),
        ("first_seen_at", "invalid"),
        ("first_seen_at", b"not-text"),
        ("last_seen_at", "2026-08-03T09:00:00"),
    ],
)
def test_list_wraps_malformed_persisted_catalog_rows(
    tmp_path: Path,
    column: str,
    value: object,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    store.record_discovery((create_reference("p1"),), _FIRST)
    with open_database(path) as connection:
        connection.execute(f"UPDATE catalog_entries SET {column} = ?", (value,))
        connection.commit()

    with pytest.raises(CatalogStoreError, match="invalid persisted") as captured:
        store.list_entries(CATALOG_PROVIDER_ID)

    assert captured.value.__cause__ is not None


def test_record_wraps_malformed_existing_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    store = SqliteCatalogStore(path)
    reference = create_reference("p1")
    store.record_discovery((reference,), _FIRST)
    with open_database(path) as connection:
        connection.execute(
            "UPDATE catalog_entries SET last_seen_at = 'invalid'"
        )
        connection.commit()

    with pytest.raises(CatalogStoreError, match="invalid persisted") as captured:
        store.record_discovery((reference,), _LATER)

    assert captured.value.__cause__ is not None
