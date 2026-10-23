"""Bounded catalog projections and four explainable ranking signals."""
import re
from collections import Counter
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.product import Product
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.commerce import CommercePolicy
from app.schemas.commerce import StoreProduct, RankedProduct, ShoppingIntent

CATALOG_LIMIT = 500
STOP_WORDS = {"i", "a", "an", "the", "want", "need", "buy", "find", "me", "show", "for", "and", "or", "with", "under", "below", "budget", "inr", "rs", "please", "some", "to", "of", "products", "product", "items", "shopping"}


def tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[\w]+", text.casefold()) if word not in STOP_WORDS and not word.isdigit()}


def local_intent(query: str) -> ShoppingIntent:
    match = re.search(r"(?:under|below|budget(?:\s+of)?|up to)\s*(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d{1,2})?)", query, re.I)
    amount = int(Decimal(match[1].replace(",", "")) * 100) if match else None
    if amount is not None and not 1 <= amount <= 100000000:
        amount = None
    return ShoppingIntent(terms=sorted(tokens(query))[:12], budget_paise=amount)


def projection(product: Product) -> StoreProduct:
    return StoreProduct(id=product.id, name=product.name, description=product.description or "",
                        category=product.category, price_paise=int(product.selling_price * 100),
                        available=product.inventory.available_quantity if product.inventory else 0)


async def catalog(session: AsyncSession, merchant_id: int) -> tuple[list[StoreProduct], bool]:
    rows = list((await session.scalars(select(Product).where(Product.merchant_id == merchant_id,
        Product.status == "active", Product.selling_price > 0).options(selectinload(Product.inventory))
        .order_by(Product.id).limit(CATALOG_LIMIT + 1))).all())
    return [projection(row) for row in rows[:CATALOG_LIMIT]], len(rows) > CATALOG_LIMIT


async def co_purchases(session: AsyncSession, merchant_id: int, anchor: int | None) -> Counter[int]:
    if anchor is None:
        return Counter()
    # Only completed orders contribute. Imported/synthetic data remains historical evidence,
    # not proof of measured recommendation lift. Test checkouts never create these orders.
    order_ids = select(OrderItem.order_id).join(Order).where(
        Order.merchant_id == merchant_id, Order.status == "delivered", OrderItem.product_id == anchor
    ).order_by(OrderItem.order_id.desc()).limit(1000)
    product_ids = (await session.scalars(select(OrderItem.product_id).join(Order).where(
        Order.merchant_id == merchant_id, OrderItem.order_id.in_(order_ids),
        OrderItem.product_id != anchor).limit(20000))).all()
    return Counter(product_ids)


def rank(products: list[StoreProduct], intent: ShoppingIntent, policy: CommercePolicy,
         pairs: Counter[int], anchor: StoreProduct | None = None,
         behavioral: dict[int, float] | None = None, semantic: dict[int, float] | None = None,
         compatibility: dict[int, float] | None = None) -> list[RankedProduct]:
    terms = tokens(" ".join(intent.terms))
    blocked = set(policy.blocked_categories)
    ranked: list[RankedProduct] = []
    for product in products:
        if product.available < 1 or product.category.casefold() in blocked or product.id == (anchor.id if anchor else None):
            continue
        if intent.budget_paise is not None and product.price_paise > min(intent.budget_paise, policy.max_spend_paise):
            continue
        text = tokens(f"{product.name} {product.description} {product.category}")
        overlap = len(terms & text) / max(1, len(terms))
        category_match = bool(terms & tokens(product.category)) or bool(anchor and product.category == anchor.category)
        related = pairs.get(product.id, 0)
        behavior_score = (behavioral or {}).get(product.id, 0)
        semantic_score = (semantic or {}).get(product.id, 0)
        compatibility_score = (compatibility or {}).get(product.id, 0)
        if terms and not overlap and not category_match and not related and behavior_score < .5 and semantic_score < .5 and not compatibility_score:
            continue
        score = overlap * 4 + int(category_match) + min(related, 10) * .2 + behavior_score + semantic_score * 2 + compatibility_score
        reasons = []
        if overlap:
            reasons.append("Matches your search terms")
        if category_match:
            reasons.append("Relevant category")
        if related:
            reasons.append(f"Appears in {related} completed-order co-purchase lines")
        if compatibility_score:
            reasons.append("Merchant-reviewed category compatibility")
        if behavior_score >= .5:
            reasons.append("Related by experimental trained co-purchase model")
        if semantic_score >= .5:
            reasons.append("Semantic similarity from the configured embedding model")
        if product.id in policy.boosted_product_ids:
            score *= 1.35
            reasons.append("Merchant featured product (1.35× ranking boost)")
        reasons.append("In stock and within applicable budget")
        ranked.append(RankedProduct(**product.model_dump(), score=round(score, 4), reasons=reasons))
    return sorted(ranked, key=lambda item: (-item.score, item.price_paise, item.id))[:24]
