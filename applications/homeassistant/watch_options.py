"""Pure parsing of native Supervisor personal-watch options."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from core.domain import Currency, Money
from core.watch import WatchCategoryRule
from infrastructure.providers.lidl import LidlWatchPreferenceSource

_PERSONAL_WATCH_KEYS = frozenset({"favorite_product_urls", "hidden_product_urls", "target_prices", "watch_category_rules", "included_categories"})
_DEFAULT_CATEGORIES = (
    WatchCategoryRule("zahrada", ("sekačka", "křovinořez", "řetězová pila", "na větve", "zavlažovací", "plotostřih")),
    WatchCategoryRule("akumulatory_nabijecky", ("akumulátor", "akumulátory", "nabíječka", "nabíječky")),
    WatchCategoryRule("prislusenstvi", ("sada bitů", "vrtáky", "vrtáků", "kotouč", "kotouče", "brusný papír", "příslušenství")),
    WatchCategoryRule("pracovni_odevy", ("pracovní kalhoty", "pracovní ponožky", "mikina", "pracovní rukavice", "pracovní bermudy", "pracovní kratasy")),
)


@dataclass(frozen=True, slots=True)
class _PersonalWatchOptions:
    """Retain validated immutable user settings without opening external state."""

    favorites: tuple[str, ...] = ()
    hidden: tuple[str, ...] = ()
    targets: tuple[tuple[str, Money], ...] = ()
    categories: tuple[WatchCategoryRule, ...] = _DEFAULT_CATEGORIES
    included: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.source()

    def source(self) -> LidlWatchPreferenceSource:
        """Create the side-effect-free URL resolver used by HA composition."""
        return LidlWatchPreferenceSource(self.favorites, self.hidden, self.targets, self.categories, self.included)

    @property
    def active(self) -> bool:
        """Keep category definitions alone from changing legacy output."""
        return bool(self.favorites or self.hidden or self.targets or self.included)


def _parse_personal_watch(document: Mapping[str, object]) -> _PersonalWatchOptions | None:
    categories = _DEFAULT_CATEGORIES
    if "watch_category_rules" in document:
        raw = _object_list(document["watch_category_rules"], {"name", "keywords"}, {"name", "keywords"})
        categories = tuple(WatchCategoryRule(row["name"], _strings(row["keywords"])) for row in raw)
    targets = []
    for row in _object_list(document.get("target_prices", []), {"url", "amount", "currency"}, {"url", "amount"}):
        if not isinstance(row["amount"], str):
            raise TypeError("target amount must be a decimal string")
        amount = Decimal(row["amount"])
        currency = Currency(row.get("currency", "CZK"))
        if currency not in (Currency.CZK, Currency.EUR):
            raise ValueError("personal target currency must be CZK or EUR")
        targets.append((row["url"], Money(amount, currency)))
    options = _PersonalWatchOptions(
        _strings(document.get("favorite_product_urls", [])), _strings(document.get("hidden_product_urls", [])),
        tuple(targets), categories, _strings(document.get("included_categories", [])),
    )
    return options if options.active else None


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise TypeError("personal watch lists must contain strings")
    return tuple(value)


def _object_list(value: object, allowed: set[str], required: set[str]) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise TypeError("personal watch entries must be a list")
    for row in value:
        if not isinstance(row, Mapping) or not required.issubset(row) or not set(row).issubset(allowed):
            raise ValueError("personal watch entry has missing or unknown fields")
    return tuple(value)
