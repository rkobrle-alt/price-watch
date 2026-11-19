"""Deterministic daily discount digest generation."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import cast

from core.domain import Money, Percentage, Product, ProductId
from core.promotions import DailyPromotion
from core.state import StateSnapshot
from core.pricing import PriceHistoryAssessment
from core.watch import DigestWatchPreferences, DigestWatchPolicy
from core.notifications.watch_format import _watch_policy, _personal_groups, _watch_details
from core.notifications.price_history_format import _format_price_history, _price_value_sort_key

_EMPTY_MESSAGE = "No currently available products match the discount threshold."


@dataclass(frozen=True, slots=True)
class DailyDiscountDigest:
    """An immutable channel-neutral daily discount summary."""

    calendar_date: date
    created_at: datetime
    products: tuple[Product, ...]
    message: str
    promotion: DailyPromotion | None = None
    new_product_ids: tuple[ProductId, ...] = ()
    price_assessments: tuple[PriceHistoryAssessment, ...] = ()
    watch_preferences: DigestWatchPreferences | None = None
    baseline_product_ids: tuple[ProductId, ...] | None = None

    def __post_init__(self) -> None:
        """Validate digest values without performing side effects."""
        _validate_date(self.calendar_date, "calendar_date")
        _validate_timestamp(self.created_at, "created_at")
        _validate_products(self.products)
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")
        if not self.message.strip():
            raise ValueError("message cannot be blank")
        if self.promotion is not None and not isinstance(
            self.promotion,
            DailyPromotion,
        ):
            raise TypeError("promotion must be a DailyPromotion or None")
        _validate_new_product_ids(self.new_product_ids, self.products)
        _validate_assessments(self.price_assessments, self.products, self.created_at)
        if self.watch_preferences is not None and not isinstance(self.watch_preferences, DigestWatchPreferences):
            raise TypeError("watch_preferences must be DigestWatchPreferences or None")
        if self.baseline_product_ids is not None:
            _validate_product_ids(self.baseline_product_ids, "baseline_product_ids")
            if not set(self.baseline_product_ids).issubset({p.id for p in self.products}):
                raise ValueError("baseline_product_ids must identify digest products")


class DailyDiscountDigestEngine:
    """Select qualifying products and format one deterministic digest."""

    def generate(
        self,
        snapshots: tuple[StateSnapshot, ...],
        minimum_discount: Percentage,
        calendar_date: date,
        timestamp: datetime,
        promotion: DailyPromotion | None = None,
        previous_product_ids: tuple[ProductId, ...] | None = None,
        include_freshness: bool = False,
        price_assessments: tuple[PriceHistoryAssessment, ...] | None = None,
        watch_preferences: DigestWatchPreferences | None = None,
    ) -> DailyDiscountDigest:
        """Generate a digest from validated latest product snapshots."""
        _validate_snapshots(snapshots)
        if not isinstance(include_freshness, bool):
            raise TypeError("include_freshness must be a bool")
        if not isinstance(minimum_discount, Percentage):
            raise TypeError("minimum_discount must be a Percentage")
        _validate_date(calendar_date, "calendar_date")
        _validate_timestamp(timestamp, "timestamp")
        if promotion is not None and not isinstance(promotion, DailyPromotion):
            raise TypeError("promotion must be a DailyPromotion or None")
        _validate_previous_product_ids(previous_product_ids)
        personal = _watch_policy(watch_preferences, snapshots)
        observations = {snapshot.product.id: snapshot.timestamp for snapshot in snapshots}
        products = tuple(
            sorted(
                (
                    snapshot.product
                    for snapshot in snapshots
                    if (personal.selected(snapshot.product, minimum_discount) if personal is not None else _qualifies(snapshot.product, minimum_discount))
                ),
                key=lambda product: (
                    -product.discount_percent.value,
                    product.name.casefold(),
                    str(product.id.value),
                ),
            )
        )
        evidence = None
        if price_assessments is not None:
            observations = {snapshot.product.id: snapshot.timestamp for snapshot in snapshots}
            _validate_assessments(price_assessments, products, timestamp, observations, required=True)
            evidence = {assessment.product_id: assessment for assessment in price_assessments}
            products = tuple(sorted(products, key=lambda product: (
                *_price_value_sort_key(evidence[product.id]), -product.discount_percent.value,
                product.name.casefold(), str(product.id.value),
            )))
        if personal is not None:
            products = tuple(sorted(products, key=lambda product: personal.priority(product, observations[product.id], timestamp)))
        baseline_products = products if personal is None else tuple(p for p in products if _qualifies(p, minimum_discount))
        new_product_ids = _new_product_ids(baseline_products, previous_product_ids)
        return DailyDiscountDigest(
            calendar_date=calendar_date,
            created_at=timestamp,
            products=products,
            message=_format_message(
                calendar_date,
                minimum_discount,
                products,
                promotion,
                new_product_ids,
                (
                    {
                        snapshot.product.id: snapshot.timestamp
                        for snapshot in snapshots
                    }
                    if include_freshness or personal is not None else None
                ),
                timestamp,
                evidence,
                personal,
            ),
            promotion=promotion,
            new_product_ids=new_product_ids,
            price_assessments=() if evidence is None else tuple(evidence[p.id] for p in products),
            watch_preferences=watch_preferences,
            baseline_product_ids=None if personal is None else tuple(p.id for p in baseline_products),
        )


def _qualifies(product: Product, minimum_discount: Percentage) -> bool:
    return (
        product.availability
        and product.original_price is not None
        and product.discount_percent.value >= minimum_discount.value
    )


def _format_message(
    calendar_date: date,
    minimum_discount: Percentage,
    products: tuple[Product, ...],
    promotion: DailyPromotion | None,
    new_product_ids: tuple[ProductId, ...],
    observations: dict[ProductId, datetime] | None,
    timestamp: datetime,
    assessments: dict[ProductId, PriceHistoryAssessment] | None = None,
    personal: DigestWatchPolicy | None = None,
) -> str:
    header_lines = [
        f"Parkside daily discount digest — {calendar_date.isoformat()}" if personal is None else f"Osobní přehled Parkside — {calendar_date.isoformat()}"
    ]
    if promotion is not None:
        header_lines.append(f"Lidl daily offer: {promotion.text}")
        if promotion.url is not None:
            header_lines.append(f"Offer URL: {promotion.url}")
    header_lines.extend(
        (
            f"Minimum discount: {minimum_discount.value}%" if personal is None else f"Slevový limit pro ostatní nabídky: {minimum_discount.value}%",
            f"Discounted products: {len(products)}" if personal is None else f"Nabídky v osobním přehledu: {len(products)}",
        )
    )
    header = "\n".join(header_lines)
    if observations is not None:
        recent_count = sum(
            _is_recent(observations[product.id], timestamp) for product in products
        )
        header += (
            f"\nAktuálnost posouzena k: {timestamp.isoformat()}"
            f"\nOvěřeno v poslední hodině: {recent_count}"
            f"\nNeověřeno v poslední hodině: {len(products) - recent_count}"
            "\nČasy kontrol označují začátek úspěšného pozorovacího cyklu."
            "\nCeny a dostupnost se mohou po kontrole změnit."
        )
    if assessments is not None:
        header += (
            "\nCenová historie: minima z dostupných pozorování; obvyklá cena je medián předchozích denních cen v 90denním okně."
            "\nChybějící dny nedoplňujeme; dostupné období neznamená souvislé sledování."
        )
    if not products:
        empty = _EMPTY_MESSAGE if personal is None else "Žádné dostupné nabídky neodpovídají osobnímu výběru."
        return f"{header}\n\n{empty}"
    if personal is not None:
        sections = tuple(_format_section(title, items, observations, timestamp, assessments, personal) for title, items in _personal_groups(products, new_product_ids, personal, observations, timestamp))
        return f"{header}\n\n" + "\n\n".join(sections)
    new_identifiers = set(new_product_ids)
    new_products = tuple(
        product for product in products if product.id in new_identifiers
    )
    other_products = tuple(
        product for product in products if product.id not in new_identifiers
    )
    sections = []
    if new_products:
        sections.append(
            _format_section(
                "🆕 NOVĚ VE SLEVĚ", new_products, observations, timestamp, assessments,
            )
        )
    if other_products:
        sections.append(
            _format_section(
                "OSTATNÍ AKTUÁLNÍ SLEVY", other_products, observations, timestamp, assessments,
            )
        )
    return f"{header}\n\n" + "\n\n".join(sections)


def _format_section(
    title: str,
    products: tuple[Product, ...],
    observations: dict[ProductId, datetime] | None,
    timestamp: datetime,
    assessments: dict[ProductId, PriceHistoryAssessment] | None = None,
    personal: DigestWatchPolicy | None = None,
) -> str:
    blocks = tuple(
        _format_product(index, product, observations, timestamp, assessments, personal)
        for index, product in enumerate(products, start=1)
    )
    return f"{title} ({len(products)})\n\n" + "\n\n".join(blocks)


def _format_product(
    index: int,
    product: Product,
    observations: dict[ProductId, datetime] | None,
    timestamp: datetime,
    assessments: dict[ProductId, PriceHistoryAssessment] | None = None,
    personal: DigestWatchPolicy | None = None,
) -> str:
    reference = product.original_price
    reference_text = "neuvedena" if reference is None else f"{reference.amount} {reference.currency.value}"
    message = (
        f"{index}. {product.name}\n"
        f"Current price: {product.current_price.amount} {product.currency.value}\n"
        f"Reference price: {reference_text}\n"
        f"Discount: {product.discount_percent.value}%\n"
        f"URL: {product.url}"
    )
    if observations is not None:
        observed_at = observations[product.id]
        label = (
            "OVĚŘENO V POSLEDNÍ HODINĚ"
            if _is_recent(observed_at, timestamp)
            else "NEOVĚŘENO V POSLEDNÍ HODINĚ — cena a dostupnost mohou být zastaralé"
        )
        message += f"\n{label}\nPoslední úspěšná kontrola: {observed_at.isoformat()}"
    if assessments is not None:
        message += "\n" + _format_price_history(assessments[product.id])
    if personal is not None:
        message += "\n" + _watch_details(product, personal, observations[product.id], timestamp)
    return message


def _is_recent(observed_at: datetime, timestamp: datetime) -> bool:
    return timedelta(0) <= timestamp - observed_at <= timedelta(hours=1)


def _validate_snapshots(value: object) -> None:
    if not isinstance(value, tuple):
        raise TypeError("snapshots must be a tuple")
    identifiers = set()
    for snapshot in value:
        if not isinstance(snapshot, StateSnapshot):
            raise TypeError("snapshots must contain StateSnapshot values")
        if snapshot.product.id in identifiers:
            raise ValueError("snapshots must contain unique product identifiers")
        identifiers.add(snapshot.product.id)


def _validate_products(value: object) -> None:
    if not isinstance(value, tuple):
        raise TypeError("products must be a tuple")
    if not all(isinstance(product, Product) for product in value):
        raise TypeError("products must contain Product values")


def _validate_previous_product_ids(
    value: tuple[ProductId, ...] | None,
) -> None:
    if value is None:
        return
    _validate_product_ids(value, "previous_product_ids")


def _validate_new_product_ids(
    value: object,
    products: tuple[Product, ...],
) -> None:
    _validate_product_ids(value, "new_product_ids")
    product_identifiers = {product.id for product in products}
    if not set(value).issubset(product_identifiers):
        raise ValueError("new_product_ids must identify digest products")


def _validate_product_ids(value: object, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    if not all(isinstance(identifier, ProductId) for identifier in value):
        raise TypeError(f"{name} must contain ProductId values")
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must contain unique identifiers")


def _new_product_ids(
    products: tuple[Product, ...],
    previous_product_ids: tuple[ProductId, ...] | None,
) -> tuple[ProductId, ...]:
    if previous_product_ids is None:
        return ()
    previous = set(previous_product_ids)
    return tuple(product.id for product in products if product.id not in previous)


def _validate_date(value: object, name: str) -> None:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{name} must be a date")


def _validate_timestamp(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _validate_assessments(
    value: object, products: tuple[Product, ...], timestamp: datetime,
    observations: dict[ProductId, datetime] | None = None, *, required: bool = False,
) -> None:
    if not isinstance(value, tuple) or not all(isinstance(a, PriceHistoryAssessment) for a in value):
        raise TypeError("price_assessments must be a tuple of PriceHistoryAssessment")
    identifiers = {a.product_id for a in value}
    if len(identifiers) != len(value):
        raise ValueError("price assessments must identify unique products")
    if required or value:
        if identifiers != {p.id for p in products}:
            raise ValueError("price assessments must match all digest products")
        by_id = {p.id: p for p in products}
        for assessment in value:
            if assessment.current_price != by_id[assessment.product_id].current_price or assessment.assessed_at.astimezone(UTC) != timestamp.astimezone(UTC):
                raise ValueError("price assessment does not match current price or assessment time")
            if observations is not None and assessment.observed_at.astimezone(UTC) != observations[assessment.product_id].astimezone(UTC):
                raise ValueError("price assessment must match the current observation time")
