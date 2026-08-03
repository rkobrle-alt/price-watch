"""Tests for provider-neutral catalog Core contracts."""

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

import core.catalog as catalog_api
from core.catalog import (
    CatalogEntry,
    CatalogError,
    CatalogStore,
    CatalogStoreError,
    ProductCatalog,
    ProductReference,
)
from core.domain import ProviderId


class _Catalog:
    def discover(self) -> tuple[ProductReference, ...]:
        return ()


def _as_catalog(catalog: ProductCatalog) -> ProductCatalog:
    return catalog


def test_catalog_public_api_is_explicit() -> None:
    assert catalog_api.__all__ == [
        "CatalogEntry",
        "CatalogError",
        "CatalogStore",
        "CatalogStoreError",
        "ProductCatalog",
        "ProductReference",
    ]
    assert catalog_api.CatalogEntry is CatalogEntry
    assert catalog_api.CatalogError is CatalogError
    assert catalog_api.CatalogStore is CatalogStore
    assert catalog_api.CatalogStoreError is CatalogStoreError
    assert catalog_api.ProductCatalog is ProductCatalog
    assert catalog_api.ProductReference is ProductReference


def test_product_catalog_is_a_structural_protocol() -> None:
    catalog = _Catalog()

    assert _as_catalog(catalog) is catalog


def test_catalog_error_is_a_runtime_error() -> None:
    assert issubclass(CatalogError, RuntimeError)


def test_product_reference_is_immutable_and_compares_by_value() -> None:
    provider_id = ProviderId(uuid4())
    reference = ProductReference(provider_id, "p123", "https://lidl.cz/p/item/p123")

    assert reference == ProductReference(
        provider_id,
        "p123",
        "https://lidl.cz/p/item/p123",
    )
    with pytest.raises(FrozenInstanceError):
        reference.external_id = "p456"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_id", uuid4()),
        ("external_id", 123),
        ("url", None),
    ],
)
def test_product_reference_rejects_invalid_types(field: str, value: object) -> None:
    arguments: dict[str, object] = {
        "provider_id": ProviderId(uuid4()),
        "external_id": "p123",
        "url": "https://lidl.cz/p/item/p123",
    }
    arguments[field] = value

    with pytest.raises(TypeError, match=field):
        ProductReference(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("external_id", ""),
        ("external_id", " "),
        ("url", ""),
        ("url", "  "),
    ],
)
def test_product_reference_rejects_blank_values(field: str, value: str) -> None:
    arguments = {
        "provider_id": ProviderId(uuid4()),
        "external_id": "p123",
        "url": "https://lidl.cz/p/item/p123",
    }
    arguments[field] = value

    with pytest.raises(ValueError, match=field):
        ProductReference(**arguments)
