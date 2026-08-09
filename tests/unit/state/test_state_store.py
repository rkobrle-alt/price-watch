"""Unit tests for State Store abstractions and memory implementation."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from unittest import TestCase
from uuid import uuid4

import core.state as state_api
import infrastructure.persistence.memory as memory_api
from core.domain import ProductId
from core.state import StateSnapshot, StateStore, StateStoreError
from infrastructure.persistence.memory import InMemoryStateStore
from tests.unit.state.helpers import TIMESTAMP, create_product


class StateSnapshotTests(TestCase):
    """Verify snapshot invariants and immutability."""

    def test_contains_product_and_caller_supplied_timestamp(self) -> None:
        product = create_product()
        snapshot = StateSnapshot(product, TIMESTAMP)

        self.assertIs(snapshot.product, product)
        self.assertEqual(snapshot.timestamp, TIMESTAMP)
        with self.assertRaises(FrozenInstanceError):
            snapshot.timestamp = TIMESTAMP + timedelta(seconds=1)  # type: ignore[misc]

    def test_rejects_non_product_argument_with_type_error(self) -> None:
        with self.assertRaisesRegex(TypeError, "product must be a Product"):
            StateSnapshot("product", TIMESTAMP)  # type: ignore[arg-type]

    def test_rejects_non_datetime_timestamp_with_type_error(self) -> None:
        with self.assertRaisesRegex(TypeError, "timestamp must be a datetime"):
            StateSnapshot(create_product(), "now")  # type: ignore[arg-type]

    def test_rejects_naive_timestamp_with_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be timezone-aware"):
            StateSnapshot(create_product(), datetime(2026, 7, 30, 12, 0))


class InMemoryStateStoreTests(TestCase):
    """Verify latest-snapshot storage and public argument validation."""

    def setUp(self) -> None:
        """Create an empty store for each test."""
        self.store = InMemoryStateStore()

    def test_satisfies_state_store_protocol_and_saves_and_loads(self) -> None:
        typed_store: StateStore = self.store
        snapshot = StateSnapshot(create_product(), TIMESTAMP)

        typed_store.save(snapshot)

        self.assertIs(typed_store.load(snapshot.product.id), snapshot)

    def test_unknown_product_returns_none(self) -> None:
        self.assertIsNone(self.store.load(ProductId(uuid4())))

    def test_last_write_wins_without_timestamp_ordering(self) -> None:
        product_id = ProductId(uuid4())
        newer_timestamp = TIMESTAMP
        older_timestamp = TIMESTAMP - timedelta(days=1)
        first = StateSnapshot(
            create_product(product_id=product_id, amount="100"),
            newer_timestamp,
        )
        replacement = StateSnapshot(
            create_product(product_id=product_id, amount="90"),
            older_timestamp,
        )

        self.store.save(first)
        self.store.save(replacement)

        loaded = self.store.load(product_id)
        self.assertIs(loaded, replacement)
        self.assertEqual(loaded.timestamp, older_timestamp)

    def test_load_rejects_invalid_product_id_type(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be a ProductId"):
            self.store.load("id")  # type: ignore[arg-type]

    def test_save_rejects_invalid_snapshot_type(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be a StateSnapshot"):
            self.store.save("snapshot")  # type: ignore[arg-type]


class StateStorePublicApiTests(TestCase):
    """Verify Core and Infrastructure public exports."""

    def test_core_state_exports(self) -> None:
        expected = {
            "LatestSnapshotReader",
            "ObservationHistory",
            "ObservationStatistics",
            "ObservationStatisticsReader",
            "StateSnapshot",
            "StateStore",
            "StateStoreError",
        }

        self.assertEqual(set(state_api.__all__), expected)
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue(getattr(state_api, name).__doc__)

    def test_memory_store_export(self) -> None:
        self.assertEqual(memory_api.__all__, ["InMemoryStateStore"])
        self.assertIs(memory_api.InMemoryStateStore, InMemoryStateStore)
        self.assertTrue(InMemoryStateStore.__doc__)

    def test_state_store_error_is_an_exception(self) -> None:
        self.assertIsInstance(StateStoreError("persistence failed"), Exception)
