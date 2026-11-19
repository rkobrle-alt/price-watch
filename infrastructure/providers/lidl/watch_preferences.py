"""Resolve user product links without binding Core to Lidl URL structure."""

import re
from urllib.parse import urlsplit

from core.catalog import ProductReference
from core.domain import Money
from core.state import StateSnapshot
from core.watch import DigestWatchPreferences, WatchCategoryRule, WatchProductPreference
from infrastructure.providers.lidl.provider import LidlParksideProvider


class LidlWatchPreferenceSource:
    """Match stable p-identifiers across slug changes and tracking links."""

    def __init__(
        self, favorite_urls: tuple[str, ...] = (), hidden_urls: tuple[str, ...] = (),
        target_prices: tuple[tuple[str, Money], ...] = (),
        category_rules: tuple[WatchCategoryRule, ...] = (), included_categories: tuple[str, ...] = (),
    ) -> None:
        """Validate durable option values without network or database access."""
        self._favorites = _references(favorite_urls)
        self._hidden = _references(hidden_urls)
        if not isinstance(target_prices, tuple) or not all(isinstance(p, tuple) and len(p) == 2 and isinstance(p[1], Money) for p in target_prices):
            raise TypeError("target_prices must be tuples of product URL and Money")
        targets = _references(tuple(pair[0] for pair in target_prices))
        self._targets = {key: price for key, (_, price) in zip(targets, target_prices)}
        self._seed = {**self._favorites, **targets}
        validated = DigestWatchPreferences((), category_rules, included_categories)
        self._categories, self._included = validated.category_rules, validated.included_categories

    def seed_references(self) -> tuple[ProductReference, ...]:
        """Return nonhidden explicit watches for first discovery only."""
        return tuple(reference for key, reference in self._seed.items() if key not in self._hidden)

    def resolve(self, snapshots: tuple[StateSnapshot, ...]) -> DigestWatchPreferences:
        """Resolve preferences only against the known Lidl provider identity."""
        if not isinstance(snapshots, tuple) or not all(isinstance(s, StateSnapshot) for s in snapshots):
            raise TypeError("snapshots must be a tuple of StateSnapshot")
        if len({s.product.id for s in snapshots}) != len(snapshots):
            raise ValueError("snapshot product identities must be unique")
        rules = []
        for snapshot in snapshots:
            product = snapshot.product
            if product.provider_id != LidlParksideProvider.id:
                continue
            key = _reference(product.url).external_id
            favorite, hidden, target = key in self._favorites, key in self._hidden, self._targets.get(key)
            if favorite or hidden or target is not None:
                rules.append(WatchProductPreference(product.id, favorite, target, hidden))
        return DigestWatchPreferences(tuple(rules), self._categories, self._included)


def _references(urls: tuple[str, ...]) -> dict[str, ProductReference]:
    if not isinstance(urls, tuple) or not all(isinstance(url, str) for url in urls):
        raise TypeError("watch URLs must be a tuple of strings")
    references = tuple(_reference(url) for url in urls)
    result = {r.external_id: r for r in references}
    if len(result) != len(references):
        raise ValueError("watch URLs must have unique product identities")
    return result


def _reference(url: str) -> ProductReference:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"lidl.cz", "www.lidl.cz"} or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443}:
        raise ValueError("watch URL must use the Czech Lidl HTTPS host without credentials")
    match = re.fullmatch(r"/p/[^/]+/(p[0-9]+)", parsed.path)
    if match is None:
        raise ValueError("watch URL must identify one Lidl product")
    return ProductReference(LidlParksideProvider.id, match[1], f"https://www.lidl.cz{parsed.path}")
