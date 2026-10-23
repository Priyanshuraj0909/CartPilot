"""Grounded conversational shopping with durable context and no implicit approval."""
import re
import time
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.commerce import ShopperSession
from app.models.commerce_workflows import ShoppingConversation
from app.schemas.commerce import SearchRequest, CartRequest
from app.schemas.commerce_workflows import ChatRequest
from app.services.commerce import carts, resolution
from app.services.commerce.catalog import tokens


def draft_lines(query: str, products: list[dict], current: list[dict]) -> list[dict]:
    lines = [{"product_id": row["product_id"], "quantity": row["quantity"]} for row in current]
    if re.search(r"\b(instead|replace)\b", query):
        lines = []
    seen = set()
    for clause in re.split(r"\band\b|,(?!\d)", query)[:5]:
        terms = tokens(clause)
        scored = sorted(products, key=lambda p: (-len(tokens(p["name"]) & terms), p["id"]))
        if not scored or not (tokens(scored[0]["name"]) & terms):
            continue
        target = scored[0]
        if target["id"] in seen:
            continue
        seen.add(target["id"])
        match = re.search(r"(?:^|\badd\s+|\bput\s+)(\d+)\s+", clause.strip())
        quantity = int(match[1]) if match else 1
        existing = next((row for row in lines if row["product_id"] == target["id"]), None)
        if existing:
            existing["quantity"] += quantity
        else:
            lines.append({"product_id": target["id"], "quantity": quantity})
    if not seen:
        raise HTTPException(422, "Name an available product to add to the draft.")
    return lines


async def conversation(session: AsyncSession, shopper: ShopperSession) -> ShoppingConversation:
    record = await session.get(ShoppingConversation, shopper.token_hash, with_for_update=True)
    if record is None:
        record = ShoppingConversation(shopper_hash=shopper.token_hash, messages=[], context={}, updated_at=int(time.time()))
        session.add(record)
        await session.flush()
    return record


async def respond(session: AsyncSession, shopper: ShopperSession, body: ChatRequest) -> dict:
    from app.api.v1.commerce import search
    record = await conversation(session, shopper)
    context = dict(record.context)
    query = body.message.casefold()
    cart_id = str(body.cart_id) if body.cart_id else context.get("cart_id")
    cart = await carts.owned_cart(session, shopper, cart_id) if cart_id else None
    products = []
    actions = []
    trace = [{"step": "understand", "reason": "Intent suggests work; only application code validates state."}]
    source = "local"
    if re.search(r"\b(refund|cancel|return|payment status|recover|checkout|pay now|approve)\b", query):
        state = await resolution.eligibility(session, cart) if cart else None
        reply = "Choose a cart first, then review its available actions."
        if state:
            reply = f"Your cart is {cart.status.replace('_', ' ')}. Remaining refundable balance: ₹{state['refundable_paise']/100:.2f}. Review the action panel to explicitly confirm cancellation, recovery, refund or test checkout."
            actions = [name for name in ("cancel", "refund", "recover", "return_review") if state.get("can_" + name)]
        trace.append({"step": "guard", "reason": "Conversation cannot approve a cart or authorize a financial operation."})
    elif re.search(r"\b(remove|delete)\b", query) and cart:
        if cart.status not in {"draft", "approved"}:
            raise HTTPException(409, "Resolve the active checkout before editing this cart.")
        requested = tokens(query) - {"remove", "delete", "from", "cart", "my"}
        remaining = [row for row in cart.items if not (tokens(row["name"]) & requested)]
        if len(remaining) == len(cart.items) or not remaining:
            raise HTTPException(422, "Name an item in the cart, and retain at least one item. To remove the entire cart, confirm cancellation.")
        cart = await carts.create(session, shopper, CartRequest(budget_paise=cart.budget_paise,
            items=[{"product_id": row["product_id"], "quantity": row["quantity"]} for row in remaining]), commit=False)
        reply, actions = "I prepared the revised draft. Approval is required again.", ["review_cart"]
    else:
        previous = context.get("query", "")
        followup = any(word in query for word in ("cheaper", "instead", "more options", "similar", "under", "below")) and not re.search(r"\b(mouse|keyboard|bag|bottle|lamp|journal|headphone)\b", query)
        previous = re.sub(r"(?:under|below|budget(?:\s+of)?|up to)\s*(?:₹|rs\.?|inr)?\s*[\d,]+(?:\.\d{1,2})?", "", previous, flags=re.I)
        combined = f"{previous} {body.message}" if followup and previous else body.message
        if "cheaper" in query and cart:
            context["budget_paise"] = max(1, min(line["unit_price_paise"] for line in cart.items) - 1)
        result = await search(SearchRequest(query=combined[-1000:], budget_paise=body.budget_paise or context.get("budget_paise")), shopper, session)
        products = [product.model_dump() for product in result.products]
        source = result.intent_source
        context.update(query=combined[-1000:], budget_paise=result.budget_paise)
        reply = f"I found {len(products)} in-stock options within ₹{(result.budget_paise or 0)/100:.2f}. Select products or ask me to add a matching item to a draft cart." if products else result.message
        if products and re.search(r"\b(add|put|build|create cart|replace)\b", query):
            if cart and cart.status not in {"draft", "approved", "cancelled", "simulated_refunded", "test_refunded"}:
                raise HTTPException(409, "Resolve the active or paid checkout before building a replacement cart.")
            lines = draft_lines(query, products, cart.items if cart and cart.status in {"draft", "approved"} else [])
            try:
                request = CartRequest(budget_paise=result.budget_paise, items=lines)
            except ValueError:
                raise HTTPException(422, "The draft exceeds cart quantity or line limits.") from None
            cart = await carts.create(session, shopper, request, commit=False)
            context["cart_id"] = cart.id
            reply = "I prepared a fresh server-priced draft. Review and approve it before separately confirming checkout."
            actions = ["review_cart"]
            trace.append({"step": "draft", "reason": "Application recalculated prices, category restrictions, stock and budget."})
        trace.append({"step": "discover", "reason": "Ranked current catalog using applicable category, behavioral, semantic and business gates."})
    if cart:
        context["cart_id"] = cart.id
    record.messages = (list(record.messages) + [{"role": "user", "text": body.message}, {"role": "assistant", "text": reply}])[-40:]
    record.context, record.updated_at = context, int(time.time())
    await session.commit()
    return {"message": reply, "products": products, "cart": carts.response(cart).model_dump() if cart else None,
        "actions": actions, "trace": trace, "intent_source": source, "history": record.messages}
