"""Application-computed recovery discounts with fresh stock/cost and retained margin."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from app.models.commerce import ShoppingCart, ShopperSession
from app.models.commerce_workflows import CommerceOperation
from app.schemas.commerce import CartRequest
from app.services.commerce import carts, ledger
from app.services.commerce.merchandising import rules_for, active_rule
import time
from uuid import uuid4


async def preview(session: AsyncSession, cart: ShoppingCart) -> dict:
    if cart.status not in {"draft", "approved", "cancelled"}:
        return {"eligible": False, "reason": "Resolve the active or paid checkout before applying an offer."}
    rules = await rules_for(session, cart.merchant_id)
    allowed = {rule["category"].casefold(): rule["discount_percent"] for rule in rules.growth_rules
        if active_rule(rule) and rule["kind"] == "recovery_offer" and rule["discount_percent"] > 0}
    products = (await session.scalars(select(Product).where(Product.merchant_id == cart.merchant_id,
        Product.id.in_([row["product_id"] for row in cart.items])))).all()
    discounts = {str(p.id): allowed[p.category.casefold()] for p in products if p.category.casefold() in allowed}
    if not discounts:
        return {"eligible": False, "reason": "No enabled merchant recovery rule applies to this cart."}
    body = CartRequest(budget_paise=cart.budget_paise,
        items=[{"product_id": row["product_id"], "quantity": row["quantity"]} for row in cart.items])
    try:
        policy = await carts.policy_for(session, cart.merchant_id)
        original = await carts.price_lines(session, cart.merchant_id, body, policy)
        lines = await carts.price_lines(session, cart.merchant_id, body, policy, discounts)
    except HTTPException:
        return {"eligible": False, "reason": "Fresh inventory, price, cost or margin checks block an offer."}
    total = sum(row["subtotal_paise"] for row in lines)
    saving = sum(row["subtotal_paise"] for row in original) - total
    return {"eligible": saving > 0, "discounts": discounts, "items": lines, "total_paise": total,
        "saving_paise": saving, "reason": "Merchant-configured discount bounded by stock, cost and retained margin. Acceptance creates a new draft; it does not change catalog prices."}


async def accept(session: AsyncSession, shopper: ShopperSession, cart: ShoppingCart, request_key: str) -> ShoppingCart:
    cart = await carts.owned_cart(session, shopper, cart.id)
    existing = await session.scalar(select(CommerceOperation).where(CommerceOperation.cart_id == cart.id,
        CommerceOperation.request_key == request_key))
    if existing:
        if existing.kind != "offer" or not existing.details.get("cart_id"):
            raise HTTPException(409, "Request key already identifies a different operation.")
        return await carts.owned_cart(session, shopper, existing.details["cart_id"])
    offer = await preview(session, cart)
    if not offer["eligible"]:
        raise HTTPException(409, offer["reason"])
    fresh = await carts.create(session, shopper, CartRequest(budget_paise=cart.budget_paise,
        items=[{"product_id": row["product_id"], "quantity": row["quantity"]} for row in cart.items]), discounts=offer["discounts"], commit=False)
    session.add(CommerceOperation(id=str(uuid4()), cart_id=cart.id, request_key=request_key,
        kind="offer", status="succeeded", amount_paise=offer["saving_paise"], provider_id=None,
        details={"cart_id": fresh.id}, created_at=int(time.time())))
    await ledger.append(session, cart, "recovery_offer_accepted", {"new_cart_id": fresh.id, "saving_paise": offer["saving_paise"]})
    await session.commit()
    return fresh
