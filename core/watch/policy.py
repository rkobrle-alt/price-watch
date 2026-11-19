"""Personal selection, category classification and exact target comparisons."""

from datetime import UTC, datetime, timedelta

from core.domain import Percentage, Product
from core.watch.model import DigestWatchPreferences, WatchProductPreference, WatchTargetStatus, _normalise


class DigestWatchPolicy:
    """Apply user choices without overriding stock or inventing fresh prices."""

    def __init__(self, preferences: DigestWatchPreferences) -> None:
        """Retain validated immutable preferences and an identity lookup."""
        if not isinstance(preferences, DigestWatchPreferences):
            raise TypeError("preferences must be DigestWatchPreferences")
        self.preferences = preferences
        self._products = {rule.product_id: rule for rule in preferences.product_rules}

    def preference(self, product: Product) -> WatchProductPreference | None:
        """Return the explicit preference for one stable product identity."""
        if not isinstance(product, Product):
            raise TypeError("product must be a Product")
        return self._products.get(product.id)

    def is_watched(self, product: Product) -> bool:
        """Identify a favorite or target watch independently from sale status."""
        rule = self.preference(product)
        return rule is not None and (rule.favorite or rule.target_price is not None)

    def categories(self, product: Product) -> tuple[str, ...]:
        """Classify complete words/phrases case- and accent-insensitively."""
        self.preference(product)
        name = f" {_normalise(product.name)} "
        matches = tuple(rule.name for rule in self.preferences.category_rules if any(f" {_normalise(k)} " in name for k in rule.keywords))
        return matches or ("ostatni",)

    def selected(self, product: Product, minimum_discount: Percentage) -> bool:
        """Let hiding win, pin explicit watches, and filter ordinary discounts."""
        rule = self.preference(product)
        if not isinstance(minimum_discount, Percentage):
            raise TypeError("minimum_discount must be Percentage")
        if not product.availability or (rule is not None and rule.hidden):
            return False
        if self.is_watched(product):
            return True
        if self.preferences.included_categories and not set(self.categories(product)).intersection(self.preferences.included_categories):
            return False
        return product.original_price is not None and product.discount_percent.value >= minimum_discount.value

    def target_status(self, product: Product, observed_at: datetime, timestamp: datetime) -> WatchTargetStatus:
        """Compare an exact target only with current same-currency evidence."""
        rule = self.preference(product)
        for value in (observed_at, timestamp):
            if not isinstance(value, datetime):
                raise TypeError("watch timestamps must be datetime")
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("watch timestamps must be timezone-aware")
        if rule is None or rule.target_price is None:
            return WatchTargetStatus.NONE
        if rule.target_price.currency is not product.currency:
            return WatchTargetStatus.CURRENCY_MISMATCH
        age = timestamp.astimezone(UTC) - observed_at.astimezone(UTC)
        if not product.availability or not timedelta(0) <= age <= timedelta(hours=1):
            return WatchTargetStatus.UNVERIFIED
        return WatchTargetStatus.REACHED if product.current_price.amount <= rule.target_price.amount else WatchTargetStatus.WAITING

    def priority(self, product: Product, observed_at: datetime, timestamp: datetime) -> int:
        """Group fresh target hits, explicit watches and ordinary discounts."""
        if self.target_status(product, observed_at, timestamp) is WatchTargetStatus.REACHED:
            return 0
        return 1 if self.is_watched(product) else 2
