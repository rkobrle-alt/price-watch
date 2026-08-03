"""Immutable result of one catalog monitoring cycle."""

from dataclasses import dataclass

from applications.synchronization import SynchronizationResult
from core.catalog import CatalogError, ProductReference


@dataclass(frozen=True, slots=True)
class CatalogMonitoringResult:
    """Report discovery, selection and completed synchronization work."""

    discovered_references: tuple[ProductReference, ...]
    new_references: tuple[ProductReference, ...]
    refresh_references: tuple[ProductReference, ...]
    synchronization: SynchronizationResult | None
    catalog_error: CatalogError | None

    def __post_init__(self) -> None:
        """Validate immutable result member types."""
        _validate_references(self.discovered_references, "discovered_references")
        _validate_references(self.new_references, "new_references")
        _validate_references(self.refresh_references, "refresh_references")
        if self.synchronization is not None and not isinstance(
            self.synchronization,
            SynchronizationResult,
        ):
            raise TypeError(
                "synchronization must be a SynchronizationResult or None"
            )
        if self.catalog_error is not None and not isinstance(
            self.catalog_error,
            CatalogError,
        ):
            raise TypeError("catalog_error must be a CatalogError or None")


def _validate_references(value: object, name: str) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(reference, ProductReference) for reference in value
    ):
        raise TypeError(f"{name} must be a tuple of ProductReference values")
