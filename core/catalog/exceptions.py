"""Product catalog exceptions."""


class CatalogError(RuntimeError):
    """Report an operational product catalog discovery failure."""


class CatalogStoreError(Exception):
    """Report a catalog persistence, schema or persisted-data failure."""
