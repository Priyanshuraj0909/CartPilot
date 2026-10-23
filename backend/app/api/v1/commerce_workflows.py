"""Buyer lifecycle and durable conversation endpoints, using the same scoped capabilities."""
import hashlib
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_database_session
from app.api.v1.commerce import shopper, public_limit, search
from app.models.commerce import ShopperSession, ShoppingCart
from app.models.commerce_workflows import ShopperHandoff
from app.schemas.commerce import CartRequest, Confirmation, SearchRequest
from app.schemas.commerce_workflows import ChatRequest, ResolutionRequest, AddCartItem, HandoffRequest, ReplaceCartItem, RecoveryOfferRequest
from app.services.commerce import carts, ledger, conversation, resolution
from app.services.commerce import offers

router = APIRouter(prefix="/commerce", tags=["Commerce workflows"], dependencies=[Depends(public_limit)])


@router.get("/carts/{cart_id}/offer")
async def offer_preview(cart_id: str, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    return await offers.preview(session, await carts.owned_cart(session, identity, cart_id))


@router.post("/carts/{cart_id}/offer")
async def accept_offer(cart_id: str, body: RecoveryOfferRequest, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    cart = await carts.owned_cart(session, identity, cart_id)
    return carts.response(await offers.accept(session, identity, cart, body.request_key))


@router.post("/carts/{cart_id}/replace-item")
async def replace_item(cart_id: str, body: ReplaceCartItem, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    cart = await carts.owned_cart(session, identity, cart_id)
    if not any(row["product_id"] == body.original_product_id for row in cart.items):
        raise HTTPException(422, "Original product is not in this cart.")
    quantities = {}
    for row in cart.items:
        product = body.product_id if row["product_id"] == body.original_product_id else row["product_id"]
        quantities[product] = quantities.get(product, 0) + (body.quantity if row["product_id"] == body.original_product_id else row["quantity"])
    try:
        request = CartRequest(budget_paise=cart.budget_paise, items=[{"product_id": product, "quantity": quantity} for product, quantity in quantities.items()])
    except ValueError:
        raise HTTPException(422, "Replacement exceeds cart limits.") from None
    return await revise(cart_id, request, identity, session)


@router.get("/conversation")
async def get_conversation(identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)) -> dict:
    record = await conversation.conversation(session, identity)
    return {"messages": record.messages, "context": record.context}


@router.delete("/conversation")
async def clear_conversation(identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)) -> dict:
    record = await conversation.conversation(session, identity)
    record.messages, record.context = [], {}
    await session.commit()
    return {"cleared": True}


@router.post("/chat")
async def chat(body: ChatRequest, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)) -> dict:
    return await conversation.respond(session, identity, body)


@router.get("/carts")
async def list_carts(identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)) -> list:
    rows = (await session.scalars(select(ShoppingCart).where(ShoppingCart.shopper_hash == identity.token_hash,
        ShoppingCart.merchant_id == identity.merchant_id).order_by(ShoppingCart.created_at.desc()).limit(50))).all()
    return [carts.response(row) for row in rows]


@router.post("/carts/{cart_id}/revise")
async def revise(cart_id: str, body: CartRequest, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    old = await carts.owned_cart(session, identity, cart_id)
    if old.status not in {"draft", "approved"}:
        raise HTTPException(409, "Only unpaid carts can be revised. Resolve an active checkout first.")
    fresh = await carts.create(session, identity, body, commit=False)
    await ledger.append(session, old, "cart_revision", {"new_cart_id": fresh.id, "approval_reset": True})
    await session.commit()
    return carts.response(fresh)


@router.post("/carts/{cart_id}/add-item")
async def add_item(cart_id: str, body: AddCartItem, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    cart = await carts.owned_cart(session, identity, cart_id)
    lines = [{"product_id": row["product_id"], "quantity": row["quantity"]} for row in cart.items]
    existing = next((row for row in lines if row["product_id"] == body.product_id), None)
    if existing:
        existing["quantity"] += body.quantity
    else:
        lines.append({"product_id": body.product_id, "quantity": body.quantity})
    try:
        request = CartRequest(budget_paise=cart.budget_paise, items=lines)
    except ValueError:
        raise HTTPException(422, "Cart quantity or line limit exceeded.") from None
    fresh = await revise(cart_id, request, identity, session)
    if body.source == "upsell":
        new_cart = await carts.owned_cart(session, identity, fresh.id)
        line = next(row for row in new_cart.items if row["product_id"] == body.product_id)
        await ledger.append(session, new_cart, "upsell_accepted", {"product_id": body.product_id,
            "quantity_added": body.quantity, "value_paise": line["unit_price_paise"] * body.quantity,
            "source_cart_id": cart_id, "interpretation": "Recorded selection, not causal revenue uplift."})
        await session.commit()
    return fresh


@router.get("/carts/{cart_id}/suggestions")
async def suggestions(cart_id: str, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)) -> dict:
    cart = await carts.owned_cart(session, identity, cart_id)
    remaining = max(0, cart.budget_paise - cart.total_paise)
    upsells = await search(SearchRequest(query="Show products", budget_paise=max(1, remaining),
        anchor_product_id=cart.items[0]["product_id"]), identity, session)
    in_cart = {row["product_id"] for row in cart.items}
    substitutes = await search(SearchRequest(query=cart.items[0]["name"], budget_paise=cart.items[0]["unit_price_paise"],
        anchor_product_id=cart.items[0]["product_id"]), identity, session)
    return {"upsells": [row for row in upsells.products if row.id not in in_cart and row.price_paise <= remaining],
        "substitutes": [row for row in substitutes.products if row.id not in in_cart], "remaining_budget_paise": remaining}


@router.get("/carts/{cart_id}/resolution")
async def resolution_status(cart_id: str, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)) -> dict:
    return await resolution.eligibility(session, await carts.owned_cart(session, identity, cart_id))


@router.post("/carts/{cart_id}/resolution")
async def resolve(cart_id: str, body: ResolutionRequest, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)) -> dict:
    cart = await carts.owned_cart(session, identity, cart_id)
    return await resolution.execute(session, identity, cart, body)


@router.post("/carts/{cart_id}/handoff")
async def create_handoff(cart_id: str, body: Confirmation, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)) -> dict:
    cart = await carts.owned_cart(session, identity, cart_id)
    token = secrets.token_urlsafe(36)
    session.add(ShopperHandoff(token_hash=hashlib.sha256(token.encode()).hexdigest(), cart_id=cart.id,
        source_shopper_hash=identity.token_hash, expires_at=int(time.time()) + 300, redeemed=False))
    await session.commit()
    return {"path": f"/shop/{identity.merchant_id}#handoff={token}", "expires_in_seconds": 300}


@router.post("/handoff/redeem")
async def redeem_handoff(body: HandoffRequest, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    digest = hashlib.sha256(body.token.encode()).hexdigest()
    handoff = await session.get(ShopperHandoff, digest, with_for_update=True)
    if handoff is None or handoff.redeemed or handoff.expires_at <= int(time.time()):
        raise HTTPException(404, "Handoff expired or already redeemed.")
    cart = await session.scalar(select(ShoppingCart).where(ShoppingCart.id == handoff.cart_id,
        ShoppingCart.merchant_id == identity.merchant_id).with_for_update())
    if cart is None or cart.shopper_hash != handoff.source_shopper_hash:
        raise HTTPException(404, "Handoff cart unavailable.")
    claimed = await session.execute(update(ShopperHandoff).where(ShopperHandoff.token_hash == digest,
        ShopperHandoff.redeemed.is_(False)).values(redeemed=True).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        raise HTTPException(409, "Handoff already redeemed.")
    cart.shopper_hash = identity.token_hash
    if cart.status == "approved":
        cart.status = "draft"
    await ledger.append(session, cart, "browser_handoff", {"approval_reset": cart.status == "draft"})
    await session.commit()
    return carts.response(cart)
