"""Unit tests for the transport-neutral Provider SDK."""

from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

import core.provider as provider_api
from core.domain import (
    Currency,
    Money,
    Percentage,
    Product,
    ProductId,
    ProviderId,
    ValidationError,
)
from core.provider import (
    FetchResult,
    Provider,
    ProviderError,
    ProviderMetadata,
    ProviderRegistry,
)


def create_product(provider_id: ProviderId) -> Product:
    """Create a valid product for provider fetch tests."""
    return Product(
        id=ProductId(uuid4()),
        provider_id=provider_id,
        brand="Example",
        name="Coffee",
        current_price=Money(Decimal("99.90"), Currency.CZK),
        original_price=None,
        discount_percent=Percentage(Decimal("0")),
        url="https://example.test/product",
        image_url=None,
        created_at=datetime(2026, 7, 29, 10, 0, tzinfo=UTC),
    )


def create_fetch_result(provider_id: ProviderId) -> FetchResult:
    """Create a successful fetch result for provider contract tests."""
    started_at = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)
    duration = timedelta(seconds=2)
    return FetchResult(
        products=(create_product(provider_id),),
        started_at=started_at,
        finished_at=started_at + duration,
        duration=duration,
        errors=(),
    )


@dataclass(frozen=True, slots=True)
class ExampleProvider:
    """Test implementation of the structural Provider contract."""

    id: ProviderId
    display_name: str
    version: str

    def fetch(self) -> FetchResult:
        """Return a deterministic domain-only fetch result."""
        return create_fetch_result(self.id)


class ProviderContractTests(TestCase):
    """Verify provider implementations satisfy the public fetch contract."""

    def test_structural_provider_exposes_identity_and_fetch_result(self) -> None:
        implementation: Provider = ExampleProvider(
            id=ProviderId(uuid4()),
            display_name="Example Shop",
            version="1.0.0",
        )

        result = implementation.fetch()

        self.assertEqual(implementation.display_name, "Example Shop")
        self.assertEqual(implementation.version, "1.0.0")
        self.assertIsInstance(result, FetchResult)
        self.assertEqual(result.products[0].provider_id, implementation.id)


class ProviderMetadataTests(TestCase):
    """Verify provider metadata shape and immutability."""

    def test_contains_required_metadata_and_is_immutable(self) -> None:
        provider_id = ProviderId(uuid4())
        metadata = ProviderMetadata(
            id=provider_id,
            display_name="Example Shop",
            version="1.0.0",
            country="CZ",
            homepage="https://example.test",
        )

        self.assertEqual(metadata.id, provider_id)
        self.assertEqual(metadata.country, "CZ")
        self.assertEqual(metadata.homepage, "https://example.test")
        with self.assertRaises(FrozenInstanceError):
            metadata.version = "2.0.0"  # type: ignore[misc]


class FetchResultTests(TestCase):
    """Verify fetch result shape, immutability, and invariants."""

    def setUp(self) -> None:
        """Create valid fetch result inputs."""
        self.provider_id = ProviderId(uuid4())
        self.product = create_product(self.provider_id)
        self.started_at = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)
        self.finished_at = self.started_at + timedelta(seconds=3)

    def create_result(
        self,
        *,
        products: tuple[Product, ...] | object | None = None,
        started_at: datetime | object | None = None,
        finished_at: datetime | object | None = None,
        duration: timedelta | object | None = None,
        errors: tuple[ProviderError, ...] | object | None = None,
    ) -> FetchResult:
        """Create a fetch result with selected invalid or valid inputs."""
        return FetchResult(
            products=(self.product,) if products is None else products,  # type: ignore[arg-type]
            started_at=self.started_at if started_at is None else started_at,  # type: ignore[arg-type]
            finished_at=self.finished_at if finished_at is None else finished_at,  # type: ignore[arg-type]
            duration=timedelta(seconds=3) if duration is None else duration,  # type: ignore[arg-type]
            errors=() if errors is None else errors,  # type: ignore[arg-type]
        )

    def test_contains_products_timing_and_errors_and_is_immutable(self) -> None:
        error = ProviderError("partial failure")
        result = self.create_result(errors=(error,))

        self.assertEqual(result.products, (self.product,))
        self.assertEqual(result.duration, timedelta(seconds=3))
        self.assertEqual(result.errors, (error,))
        with self.assertRaises(FrozenInstanceError):
            result.errors = ()  # type: ignore[misc]

    def test_rejects_non_tuple_products(self) -> None:
        with self.assertRaisesRegex(ValidationError, "tuple of Product"):
            self.create_result(products=[self.product])

    def test_rejects_non_product_tuple_member(self) -> None:
        with self.assertRaisesRegex(ValidationError, "tuple of Product"):
            self.create_result(products=("product",))

    def test_rejects_non_tuple_errors(self) -> None:
        with self.assertRaisesRegex(ValidationError, "tuple of ProviderError"):
            self.create_result(errors=[])

    def test_rejects_non_provider_error_tuple_member(self) -> None:
        with self.assertRaisesRegex(ValidationError, "tuple of ProviderError"):
            self.create_result(errors=(ValueError("failure"),))

    def test_rejects_non_datetime_timestamps(self) -> None:
        with self.assertRaisesRegex(ValidationError, "started_at must be a datetime"):
            self.create_result(started_at="now")
        with self.assertRaisesRegex(ValidationError, "finished_at must be a datetime"):
            self.create_result(finished_at="later")

    def test_rejects_naive_timestamps(self) -> None:
        with self.assertRaisesRegex(ValidationError, "started_at must be timezone-aware"):
            self.create_result(started_at=datetime(2026, 7, 29, 10, 0))
        with self.assertRaisesRegex(ValidationError, "finished_at must be timezone-aware"):
            self.create_result(finished_at=datetime(2026, 7, 29, 10, 1))

    def test_rejects_finished_at_before_started_at(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot be before"):
            self.create_result(finished_at=self.started_at - timedelta(seconds=1))

    def test_rejects_non_timedelta_duration(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a timedelta"):
            self.create_result(duration=3)

    def test_rejects_negative_duration(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot be negative"):
            self.create_result(duration=timedelta(microseconds=-1))


class ProviderRegistryTests(TestCase):
    """Verify provider registration lifecycle."""

    def setUp(self) -> None:
        """Create an empty registry and two providers."""
        self.registry = ProviderRegistry()
        self.first = ExampleProvider(ProviderId(uuid4()), "First", "1.0")
        self.second = ExampleProvider(ProviderId(uuid4()), "Second", "2.0")

    def test_register_get_list_and_unregister(self) -> None:
        self.registry.register(self.first)
        self.registry.register(self.second)

        self.assertIs(self.registry.get(self.first.id), self.first)
        self.assertEqual(self.registry.list(), (self.first, self.second))
        self.assertIs(self.registry.unregister(self.first.id), self.first)
        self.assertEqual(self.registry.list(), (self.second,))

    def test_rejects_duplicate_registration(self) -> None:
        duplicate = ExampleProvider(self.first.id, "Duplicate", "2.0")
        self.registry.register(self.first)

        with self.assertRaisesRegex(ProviderError, "already registered"):
            self.registry.register(duplicate)

    def test_get_rejects_missing_provider(self) -> None:
        with self.assertRaisesRegex(ProviderError, "not registered") as context:
            self.registry.get(self.first.id)
        self.assertIsInstance(context.exception.__cause__, KeyError)

    def test_unregister_rejects_missing_provider(self) -> None:
        with self.assertRaisesRegex(ProviderError, "not registered") as context:
            self.registry.unregister(self.first.id)
        self.assertIsInstance(context.exception.__cause__, KeyError)


class ProviderPublicApiTests(TestCase):
    """Verify documented Provider SDK exports."""

    def test_public_exports(self) -> None:
        expected = {
            "FetchResult",
            "Provider",
            "ProviderDataError",
            "ProviderError",
            "ProviderMetadata",
            "ProviderRegistry",
            "ProviderTransportError",
        }

        self.assertEqual(set(provider_api.__all__), expected)
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue(getattr(provider_api, name).__doc__)
