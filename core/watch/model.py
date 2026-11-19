"""Immutable provider-neutral personal daily-watch preferences."""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from core.domain import Money, ProductId


class WatchTargetStatus(str, Enum):
    """Distinguish a fresh target hit from waiting or incomparable evidence."""

    NONE = "none"
    REACHED = "reached"
    WAITING = "waiting"
    UNVERIFIED = "unverified"
    CURRENCY_MISMATCH = "currency_mismatch"


@dataclass(frozen=True, slots=True)
class WatchProductPreference:
    """Attach user choices to one resolved stable product identity."""

    product_id: ProductId
    favorite: bool = False
    target_price: Money | None = None
    hidden: bool = False

    def __post_init__(self) -> None:
        """Validate explicit choices without guessing user interest."""
        if not isinstance(self.product_id, ProductId):
            raise TypeError("product_id must be a ProductId")
        if not isinstance(self.favorite, bool) or not isinstance(self.hidden, bool):
            raise TypeError("favorite and hidden must be bool")
        if self.target_price is not None and not isinstance(self.target_price, Money):
            raise TypeError("target_price must be Money or None")
        if not self.favorite and not self.hidden and self.target_price is None:
            raise ValueError("a product preference must specify a user choice")


@dataclass(frozen=True, slots=True)
class WatchCategoryRule:
    """Define a transparent name-derived category using complete phrases."""

    name: str
    keywords: tuple[str, ...]

    def __post_init__(self) -> None:
        """Require stable category names and meaningful nonempty phrases."""
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("category name must use lowercase letters, digits and underscores")
        if self.name == "ostatni":
            raise ValueError("ostatni is reserved for unmatched products")
        if not isinstance(self.keywords, tuple) or not all(isinstance(k, str) for k in self.keywords):
            raise TypeError("category keywords must be a tuple of strings")
        if not self.keywords or any(not _normalise(k) for k in self.keywords):
            raise ValueError("category keywords must contain words")


@dataclass(frozen=True, slots=True)
class DigestWatchPreferences:
    """Resolve product choices and category filters for one daily preparation."""

    product_rules: tuple[WatchProductPreference, ...] = ()
    category_rules: tuple[WatchCategoryRule, ...] = ()
    included_categories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject ambiguous identities, categories and unknown filter names."""
        for values, kind in ((self.product_rules, WatchProductPreference), (self.category_rules, WatchCategoryRule), (self.included_categories, str)):
            if not isinstance(values, tuple) or not all(isinstance(v, kind) for v in values):
                raise TypeError("watch preference collections must be typed tuples")
        identifiers = [p.product_id for p in self.product_rules]
        names = [r.name for r in self.category_rules]
        if len(set(identifiers)) != len(identifiers) or len(set(names)) != len(names):
            raise ValueError("watch product and category identities must be unique")
        if len(set(self.included_categories)) != len(self.included_categories):
            raise ValueError("included categories must be unique")
        if not set(self.included_categories).issubset(set(names) | {"ostatni"}):
            raise ValueError("included category is not defined")

    @property
    def active(self) -> bool:
        """Report whether resolved product choices or category filtering apply."""
        return bool(self.product_rules or self.included_categories)


def _normalise(value: str) -> str:
    text = "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", text))
