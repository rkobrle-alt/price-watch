"""Personal grouping and truthful target-price presentation."""

from datetime import datetime

from core.domain import Product, ProductId
from core.state import StateSnapshot
from core.watch import DigestWatchPreferences, DigestWatchPolicy, WatchTargetStatus


def _watch_policy(value: DigestWatchPreferences | None, snapshots: tuple[StateSnapshot, ...]) -> DigestWatchPolicy | None:
    if value is None:
        return None
    if not isinstance(value, DigestWatchPreferences):
        raise TypeError("watch_preferences must be DigestWatchPreferences or None")
    if not {rule.product_id for rule in value.product_rules}.issubset({s.product.id for s in snapshots}):
        raise ValueError("watch preferences must resolve against the supplied observations")
    return DigestWatchPolicy(value) if value.active else None


def _personal_groups(
    products: tuple[Product, ...], new_ids: tuple[ProductId, ...], policy: DigestWatchPolicy,
    observations: dict[ProductId, datetime], timestamp: datetime,
) -> tuple[tuple[str, tuple[Product, ...]], ...]:
    groups = [[], [], [], []]
    for product in products:
        priority = policy.priority(product, observations[product.id], timestamp)
        index = priority if priority < 2 else (2 if product.id in new_ids else 3)
        groups[index].append(product)
    titles = ("🎯 DOSAŽENÉ CÍLOVÉ CENY", "⭐ OBLÍBENÉ A HLÍDANÉ PRODUKTY", "NOVĚ V OSOBNÍM VÝBĚRU SLEV", "OSTATNÍ AKTUÁLNÍ SLEVY")
    return tuple((title, tuple(items)) for title, items in zip(titles, groups) if items)


def _watch_details(product: Product, policy: DigestWatchPolicy, observed_at: datetime, timestamp: datetime) -> str:
    lines = [f"Kategorie podle názvu: {', '.join(policy.categories(product))}"]
    preference = policy.preference(product)
    if preference is not None:
        if preference.favorite:
            lines.append("Oblíbený produkt")
        if preference.target_price is not None:
            labels = {
                WatchTargetStatus.REACHED: "DOSAŽENA — ověřeno v poslední hodině",
                WatchTargetStatus.WAITING: "čekáme na cílovou cenu",
                WatchTargetStatus.UNVERIFIED: "neověřeno — cenu nelze označit jako dosaženou",
                WatchTargetStatus.CURRENCY_MISMATCH: "jiná měna — bez automatického přepočtu",
            }
            target = preference.target_price
            lines.append(f"Cílová cena: {target.amount} {target.currency.value} — {labels[policy.target_status(product, observed_at, timestamp)]}")
    return "\n".join(lines)
