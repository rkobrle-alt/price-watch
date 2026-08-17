"""Deterministic daily discount digest generation."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import cast

from core.domain import Money, Percentage, Product, ProductId
from core.promotions import DailyPromotion
from core.state import StateSnapshot

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
    ) -> DailyDiscountDigest:
        """Generate a digest from validated latest product snapshots."""
        _validate_snapshots(snapshots)
        if not isinstance(minimum_discount, Percentage):
            raise TypeError("minimum_discount must be a Percentage")
        _validate_date(calendar_date, "calendar_date")
        _validate_timestamp(timestamp, "timestamp")
        if promotion is not None and not isinstance(promotion, DailyPromotion):
            raise TypeError("promotion must be a DailyPromotion or None")
        _validate_previous_product_ids(previous_product_ids)
        products = tuple(
            sorted(
                (
                    snapshot.product
                    for snapshot in snapshots
                    if _qualifies(snapshot.product, minimum_discount)
                ),
                key=lambda product: (
                    -product.discount_percent.value,
                    product.name.casefold(),
                    str(product.id.value),
                ),
            )
        )
        new_product_ids = _new_product_ids(products, previous_product_ids)
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
            ),
            promotion=promotion,
            new_product_ids=new_product_ids,
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
) -> str:
    header_lines = [
        f"Parkside daily discount digest — {calendar_date.isoformat()}"
    ]
    if promotion is not None:
        header_lines.append(f"Lidl daily offer: {promotion.text}")
        if promotion.url is not None:
            header_lines.append(f"Offer URL: {promotion.url}")
    header_lines.extend(
        (
            f"Minimum discount: {minimum_discount.value}%",
            f"Discounted products: {len(products)}",
        )
    )
    header = "\n".join(header_lines)
    if not products:
        return f"{header}\n\n{_EMPTY_MESSAGE}"
    new_identifiers = set(new_product_ids)
    new_products = tuple(
        product for product in products if product.id in new_identifiers
    )
    other_products = tuple(
        product for product in products if product.id not in new_identifiers
    )
    sections = []
    if new_products:
        sections.append(_format_section("🆕 NOVĚ VE SLEVĚ", new_products))
    if other_products:
        sections.append(
            _format_section("OSTATNÍ AKTUÁLNÍ SLEVY", other_products)
        )
    return f"{header}\n\n" + "\n\n".join(sections)


def _format_section(title: str, products: tuple[Product, ...]) -> str:
    blocks = tuple(
        _format_product(index, product)
        for index, product in enumerate(products, start=1)
    )
    return f"{title} ({len(products)})\n\n" + "\n\n".join(blocks)


def _format_product(index: int, product: Product) -> str:
    reference = cast(Money, product.original_price)
    return (
        f"{index}. {product.name}\n"
        f"Current price: {product.current_price.amount} {product.currency.value}\n"
        f"Reference price: {reference.amount} {reference.currency.value}\n"
        f"Discount: {product.discount_percent.value}%\n"
        f"URL: {product.url}"
    )


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
