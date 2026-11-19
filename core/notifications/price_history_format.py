"""Czech presentation of observed historical price evidence."""

from decimal import Decimal

from core.domain import Money
from core.pricing import PriceHistoryAssessment, PriceValueRating as Rating

_LABELS = {
    Rating.EXCELLENT: "Výborná cena vůči pozorované historii",
    Rating.GOOD: "Výhodná cena vůči obvyklé ceně",
    Rating.LOWER: "Mírně pod obvyklou cenou",
    Rating.NORMAL: "Na úrovni obvyklé ceny",
    Rating.ABOVE_USUAL: "Nad obvyklou cenou",
    Rating.INSUFFICIENT_HISTORY: "Nedostatek historie pro hodnocení",
    Rating.UNVERIFIED: "Neověřená aktuální cena — výhodnost nehodnotíme",
}


def _format_price_history(assessment: PriceHistoryAssessment) -> str:
    """Show metrics with sample coverage instead of claiming unseen prices."""
    lines = [
        f"Hodnocení: {_LABELS[assessment.rating]}",
        f"Minimum z pozorování za 30 dní: {_money(assessment.minimum_30)} (pozorování v {assessment.observed_days_30} dnech)",
        f"Minimum z pozorování za 90 dní: {_money(assessment.minimum_90)} (pozorování v {assessment.observed_days_90} dnech)",
        f"Obvyklá cena: {_money(assessment.usual_price)} (medián {assessment.prior_days} předchozích denních cen)",
    ]
    saving = assessment.saving_vs_usual_percent
    if saving is not None:
        label = "pod" if saving >= Decimal(0) else "nad"
        lines.append(f"Aktuální cena vůči obvyklé: {abs(saving):.2f} % {label} obvyklou cenou")
    first = "není dostupné" if assessment.first_observed_at is None else assessment.first_observed_at.isoformat()
    lines.append(f"Dostupné období historie: {assessment.history_days} dní; první záznam: {first}")
    drop = "nezaznamenáno" if assessment.last_price_drop_on is None else assessment.last_price_drop_on.isoformat()
    lines.append(f"Poslední zaznamenané zlevnění v denních cenách: {drop}")
    return "\n".join(lines)


def _price_value_sort_key(assessment: PriceHistoryAssessment) -> tuple[int, Decimal]:
    """Prioritize supported value evidence before short or stale histories."""
    ranks = tuple(Rating)
    return ranks.index(assessment.rating), -(assessment.saving_vs_usual_percent or Decimal(0))


def _money(value: Money | None) -> str:
    return "není dostatek údajů" if value is None else f"{value.amount:.2f} {value.currency.value}"
