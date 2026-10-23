"""Application-level cart policy, fresh price/stock checks and explicit state transitions."""
import time
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.product import Product
from app.models.commerce import CommercePolicy, ShoppingCart, ShopperSession
from app.schemas.commerce import CartRequest, CartLine, CartResponse
from app.services.commerce import ledger


async def policy_for(session: AsyncSession, merchant_id: int) -> CommercePolicy:
    policy = await session.get(CommercePolicy, merchant_id)
    return policy or CommercePolicy(merchant_id=merchant_id, published=False, max_spend_paise=10000000,
        blocked_categories=[], boosted_product_ids=[])


async def price_lines(session: AsyncSession, merchant_id: int, body: CartRequest,
                      policy: CommercePolicy) -> list[dict]:
    ids = [line.product_id for line in body.items]
    products = {row.id: row for row in (await session.scalars(select(Product).where(
        Product.id.in_(ids), Product.merchant_id == merchant_id).options(selectinload(Product.inventory))
        .execution_options(populate_existing=True))).all()}
    result = []
    for line in body.items:
        product = products.get(line.product_id)
        if product is None or product.status != "active":
            raise HTTPException(422, "A cart product is unavailable.")
        if product.category.casefold() in policy.blocked_categories:
            raise HTTPException(422, "A cart category is blocked by store policy.")
        available = product.inventory.available_quantity if product.inventory else 0
        price = int(product.selling_price * 100)
        if line.quantity > available or price <= 0:
            raise HTTPException(409, "Cart stock or price is no longer available.")
        result.append(CartLine(product_id=product.id, name=product.name, quantity=line.quantity,
            unit_price_paise=price, subtotal_paise=price * line.quantity).model_dump())
    total = sum(line["subtotal_paise"] for line in result)
    if total > min(body.budget_paise, policy.max_spend_paise):
        raise HTTPException(422, "Cart exceeds the shopper budget or merchant spend cap.")
    return result


async def create(session: AsyncSession, shopper: ShopperSession, body: CartRequest) -> ShoppingCart:
    policy = await policy_for(session, shopper.merchant_id)
    lines = await price_lines(session, shopper.merchant_id, body, policy)
    timestamp = int(time.time())
    cart = ShoppingCart(id=str(uuid4()), merchant_id=shopper.merchant_id, shopper_hash=shopper.token_hash,
        status="draft", items=lines, total_paise=sum(line["subtotal_paise"] for line in lines),
        budget_paise=body.budget_paise, created_at=timestamp, expires_at=timestamp + 900)
    session.add(cart)
    await session.flush()
    await ledger.append(session, cart, "intent_mandate", {"budget_paise": body.budget_paise})
    await ledger.append(session, cart, "cart_proposed", {"items": lines, "total_paise": cart.total_paise})
    await session.commit()
    return cart


async def owned_cart(session: AsyncSession, shopper: ShopperSession, cart_id: str) -> ShoppingCart:
    cart = await session.scalar(select(ShoppingCart).where(ShoppingCart.id == cart_id,
        ShoppingCart.shopper_hash == shopper.token_hash, ShoppingCart.merchant_id == shopper.merchant_id)
        .with_for_update().execution_options(populate_existing=True))
    if cart is None:
        raise HTTPException(404, "Cart not found.")
    return cart


async def revalidate(session: AsyncSession, cart: ShoppingCart) -> None:
    if cart.expires_at <= int(time.time()):
        raise HTTPException(409, "Cart expired. Build a fresh cart.")
    policy = await policy_for(session, cart.merchant_id)
    body = CartRequest(budget_paise=cart.budget_paise,
        items=[{"product_id": line["product_id"], "quantity": line["quantity"]} for line in cart.items])
    fresh = await price_lines(session, cart.merchant_id, body, policy)
    if fresh != cart.items:
        raise HTTPException(409, "Cart prices or product details changed. Build a fresh cart.")
    history = await ledger.events(session, cart.id)
    proposed = next((row for row in history if row.event == "cart_proposed"), None)
    intent = next((row for row in history if row.event == "intent_mandate"), None)
    if not ledger.verify(history) or intent is None or intent.payload != {"budget_paise": cart.budget_paise} or proposed is None or proposed.payload != {"items": cart.items, "total_paise": cart.total_paise}:
        raise HTTPException(409, "Cart audit verification failed.")


async def transition(session: AsyncSession, cart: ShoppingCart, before: str, after: str) -> None:
    claimed = await session.execute(update(ShoppingCart).where(ShoppingCart.id == cart.id,
        ShoppingCart.status == before).values(status=after).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        raise HTTPException(409, "Cart state changed. Refresh before continuing.")
    cart.status = after


def response(cart: ShoppingCart) -> CartResponse:
    return CartResponse(id=cart.id, status=cart.status, budget_paise=cart.budget_paise,
        total_paise=cart.total_paise, items=cart.items, expires_at=cart.expires_at, checkout_url=cart.checkout_url)
