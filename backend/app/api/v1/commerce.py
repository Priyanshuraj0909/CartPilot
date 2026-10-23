"""Opt-in public storefront; private shopper capabilities; authenticated merchant controls."""
import hashlib
import hmac
import json
import secrets
import time
import re
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from pydantic import Field
from fastapi.responses import PlainTextResponse
from app.api.deps import get_database_session
from app.api.v1.accounts import current_account
from app.core.config import settings
from app.models.account import Account
from app.models.merchant import Merchant
from app.models.product import Product
from app.models.commerce import CommercePolicy, ShopperSession, ShoppingCart
from app.schemas.commerce import (AuditResponse, CartRequest, CartResponse, CheckoutRequest, Confirmation,
    Contract, EventResponse, PolicyRequest, SearchRequest, SearchResponse, SessionRequest)
from app.services.commerce import carts, ledger, payments
from app.services.commerce.catalog import catalog, co_purchases, rank
from app.services.commerce.intent import understand
from app.services.auth_limits import record_attempt
from app.services.commerce.ingestion import ingest
from app.services.commerce import learning

router = APIRouter(prefix="/commerce", tags=["Buyer commerce"])


class CatalogUpload(Contract):
    csv_text: str = Field(min_length=1, max_length=1000000)


@router.get("/catalog/template", response_class=PlainTextResponse)
async def catalog_template(account: Account = Depends(current_account)) -> str:
    return "sku,name,category,description,cost_price,selling_price,quantity\nDEMO-001,Everyday Notebook,Stationery,Plain notebook,50.00,100.00,25\n"


@router.post("/catalog/import", status_code=201)
async def import_catalog(body: CatalogUpload, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)) -> dict:
    try:
        return await ingest(session, account.merchant_id, body.csv_text)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "A catalog SKU was imported concurrently. Review the catalog before retrying.") from None


async def public_limit(request: Request, session: AsyncSession = Depends(get_database_session)) -> None:
    peer = request.client.host if request.client else "unknown"
    token = request.headers.get("x-cartpilot-buyer", "")[:128]
    # Enforce both a peer budget and a shopper budget so creating fresh sessions
    # cannot bypass provider-cost/request limits. Trusted proxy setup remains required.
    now = int(time.time())
    retry = 0
    for identity, budget in ((f"commerce-peer:{peer}", 180), (f"commerce-shopper:{token or peer}", 60)):
        retry = max(retry, await record_attempt(session, hashlib.sha256(identity.encode()).hexdigest(), budget, now, 60))
    await session.commit()
    if retry:
        raise HTTPException(429, "Too many shopping requests.", headers={"Retry-After": str(retry)})


async def shopper(x_cartpilot_buyer: str = Header(""), session: AsyncSession = Depends(get_database_session)) -> ShopperSession:
    if not 20 <= len(x_cartpilot_buyer) <= 128:
        raise HTTPException(401, "Start a shopping session first.")
    record = await session.get(ShopperSession, hashlib.sha256(x_cartpilot_buyer.encode()).hexdigest())
    if record is None or record.expires_at <= int(time.time()):
        raise HTTPException(401, "Shopping session expired.")
    # Existing preview capabilities remain valid until their short expiry after unpublishing;
    # public creation stops immediately. No merchant/account access is granted by them.
    return record


async def store_access(request: Request, session: AsyncSession, merchant_id: int) -> Merchant:
    merchant = await session.get(Merchant, merchant_id)
    policy = await carts.policy_for(session, merchant_id)
    if merchant is None:
        raise HTTPException(404, "Store not found.")
    if not policy.published:
        account = await current_account(request, session)
        if account.merchant_id != merchant_id:
            raise HTTPException(404, "Store not found.")
    return merchant


@router.get("/storefront/{merchant_id}", dependencies=[Depends(public_limit)])
async def storefront(request: Request, merchant_id: int = Path(gt=0, le=2147483647), session: AsyncSession = Depends(get_database_session)) -> dict:
    store = await store_access(request, session, merchant_id)
    products, truncated = await catalog(session, merchant_id)
    policy = await carts.policy_for(session, merchant_id)
    visible = [p for p in products if p.category.casefold() not in policy.blocked_categories]
    return {"store_name": store.store_name, "currency": "INR", "products": visible, "truncated": truncated,
            "max_spend_paise": policy.max_spend_paise, "checkout_modes": ["simulation"] +
            (["razorpay_test"] if settings.BUYER_RAZORPAY_TEST_ENABLED and settings.RAZORPAY_KEY_ID.startswith("rzp_test_") and settings.RAZORPAY_KEY_SECRET.get_secret_value() else [])}


@router.post("/sessions", status_code=201, dependencies=[Depends(public_limit)])
async def start_session(body: SessionRequest, request: Request, session: AsyncSession = Depends(get_database_session)) -> dict:
    await store_access(request, session, body.merchant_id)
    token = secrets.token_urlsafe(36)
    expiry = int(time.time()) + 3600
    session.add(ShopperSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), merchant_id=body.merchant_id, expires_at=expiry))
    await session.commit()
    return {"token": token, "expires_at": expiry}


@router.post("/search", response_model=SearchResponse, dependencies=[Depends(public_limit)])
async def search(body: SearchRequest, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    products, truncated = await catalog(session, identity.merchant_id)
    policy = await carts.policy_for(session, identity.merchant_id)
    intent, source = await understand(body.query)
    caps = [policy.max_spend_paise] + [cap for cap in (body.budget_paise, intent.budget_paise) if cap is not None]
    intent.budget_paise = min(caps)
    anchor = next((p for p in products if p.id == body.anchor_product_id), None)
    if body.anchor_product_id and anchor is None:
        raise HTTPException(404, "Product not found.")
    pairs = await co_purchases(session, identity.merchant_id, body.anchor_product_id)
    behavioral, semantic = await learning.learned_scores(session, identity.merchant_id, body.query, products, body.anchor_product_id)
    ranked = rank(products, intent, policy, pairs, anchor, behavioral, semantic)
    return SearchResponse(products=ranked, message="Choose products to build a cart. Approval is required before checkout." if ranked else "No in-stock products match this request and budget. Try another search or increase your budget.",
        intent_source=source, budget_paise=intent.budget_paise, truncated=truncated)


@router.post("/carts", response_model=CartResponse, status_code=201, dependencies=[Depends(public_limit)])
async def create_cart(body: CartRequest, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    return carts.response(await carts.create(session, identity, body))


@router.get("/carts/{cart_id}", response_model=CartResponse)
async def get_cart(cart_id: str, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    return carts.response(await carts.owned_cart(session, identity, cart_id))


@router.post("/carts/{cart_id}/approve", response_model=CartResponse)
async def approve(cart_id: str, body: Confirmation, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    cart = await carts.owned_cart(session, identity, cart_id)
    if cart.status != "draft":
        raise HTTPException(409, "Only draft carts can be approved.")
    await carts.revalidate(session, cart)
    await carts.transition(session, cart, "draft", "approved")
    await ledger.append(session, cart, "cart_mandate", {"total_paise": cart.total_paise, "items": cart.items})
    await session.commit()
    return carts.response(cart)


@router.post("/carts/{cart_id}/checkout", response_model=CartResponse)
async def checkout(cart_id: str, body: CheckoutRequest, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    cart = await carts.owned_cart(session, identity, cart_id)
    if cart.status in {"simulated", "checkout_ready", "test_paid"}:
        return carts.response(cart)
    if cart.status != "approved":
        raise HTTPException(409, "Approve the cart before checkout, or review its pending checkout.")
    await carts.revalidate(session, cart)
    if body.mode == "simulation":
        await carts.transition(session, cart, "approved", "simulated")
        await ledger.append(session, cart, "payment_simulated", {"amount_paise": cart.total_paise, "currency": "INR", "real_payment": False})
        await session.commit()
        return carts.response(cart)
    payments.require_test_provider()
    # Razorpay requires link expiry at least 15 minutes in the future. Approval
    # validates the 15-minute quote; the confirmed test link gets its own 20-minute
    # payment window. This does not reserve stock or enable fulfillment.
    cart.expires_at = int(time.time()) + 1200
    await carts.transition(session, cart, "approved", "checkout_pending")
    await ledger.append(session, cart, "payment_requested", {"amount_paise": cart.total_paise, "mode": "razorpay_test", "expires_at": cart.expires_at})
    # Persist the claim before the external request. Timeout/unknown results must not
    # create another payment link on retry. Reconciliation requires provider review.
    await session.commit()
    try:
        link_id, url = await payments.create_test_link(cart)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Test checkout result is uncertain. Do not retry; review the provider using the cart reference.") from None
    cart.checkout_id, cart.checkout_url = link_id, url
    await carts.transition(session, cart, "checkout_pending", "checkout_ready")
    await ledger.append(session, cart, "payment_mandate", {"provider_id": link_id, "amount_paise": cart.total_paise, "mode": "razorpay_test"})
    await session.commit()
    return carts.response(cart)


@router.get("/carts/{cart_id}/audit", response_model=AuditResponse)
async def audit(cart_id: str, identity: ShopperSession = Depends(shopper), session: AsyncSession = Depends(get_database_session)):
    await carts.owned_cart(session, identity, cart_id)
    history = await ledger.events(session, cart_id)
    return AuditResponse(valid=ledger.verify(history), events=[EventResponse.model_validate(row, from_attributes=True) for row in history])


@router.get("/policy", response_model=PolicyRequest)
async def read_policy(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    return PolicyRequest.model_validate(await carts.policy_for(session, account.merchant_id), from_attributes=True)


@router.put("/policy", response_model=PolicyRequest)
async def save_policy(body: PolicyRequest, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    ids = body.boosted_product_ids
    if ids:
        owned = (await session.scalars(select(Product.id).where(Product.merchant_id == account.merchant_id, Product.id.in_(ids)))).all()
        if set(owned) != set(ids):
            raise HTTPException(422, "Featured products must belong to this store.")
    policy = await session.get(CommercePolicy, account.merchant_id, with_for_update=True)
    if policy is None:
        policy = CommercePolicy(merchant_id=account.merchant_id)
        session.add(policy)
    for key, value in body.model_dump().items():
        setattr(policy, key, value)
    await session.commit()
    return body


@router.get("/growth")
async def growth(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)) -> dict:
    now = int(time.time())
    counts = dict((await session.execute(select(ShoppingCart.status, func.count()).where(
        ShoppingCart.merchant_id == account.merchant_id).group_by(ShoppingCart.status))).all())
    recovery = (await session.scalars(select(ShoppingCart).where(ShoppingCart.merchant_id == account.merchant_id,
        ShoppingCart.status.in_(["draft", "approved"]), ShoppingCart.created_at <= now - 300,
        ShoppingCart.expires_at > now).order_by(ShoppingCart.created_at).limit(50))).all()
    test_value = await session.scalar(select(func.coalesce(func.sum(ShoppingCart.total_paise), 0)).where(
        ShoppingCart.merchant_id == account.merchant_id, ShoppingCart.status == "test_paid"))
    return {"counts": counts, "test_paid_value_paise": test_value, "real_revenue_paise": 0,
            "recovery": [{"cart_id": row.id, "total_paise": row.total_paise, "expires_at": row.expires_at,
                          "advice": "Shopper can resume and approve before expiry; no message has been sent."} for row in recovery],
            "recommendation_method": "Category relevance + completed-order co-purchases and optional trained Item2Vec + lexical/optional indexed semantic similarity + stock/budget/merchant boost.",
            "limitations": "Test checkout does not fulfill orders, reserve stock, send recovery messages or measure incremental revenue."}


@router.get("/models")
async def model_status(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)) -> dict:
    from app.models.commerce import CommerceModel
    rows = (await session.scalars(select(CommerceModel).where(CommerceModel.merchant_id == account.merchant_id))).all()
    return {"models": [{"kind": row.kind, "products": len(row.data.get("vectors", {})), "updated_at": row.updated_at,
        "orders": row.data.get("orders")} for row in rows], "semantic_enabled": settings.BUYER_SEMANTIC_ENABLED,
        "minimum_training_orders": learning.MIN_ORDERS}


@router.post("/models/train", dependencies=[Depends(public_limit)])
async def train_model(body: Confirmation, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)) -> dict:
    return await learning.train_for_store(session, account.merchant_id)


@router.post("/models/index", dependencies=[Depends(public_limit)])
async def index_model(body: Confirmation, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)) -> dict:
    products, _ = await catalog(session, account.merchant_id)
    return await learning.index_catalog(session, account.merchant_id, products)


@router.post("/webhooks/razorpay")
async def payment_webhook(request: Request, session: AsyncSession = Depends(get_database_session)) -> dict:
    secret = settings.RAZORPAY_WEBHOOK_SECRET.get_secret_value()
    payments.require_test_provider()
    if not secret:
        raise HTTPException(503, "Webhook verification is not configured.")
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > 65536:
            raise HTTPException(413, "Webhook is too large.")
        chunks.extend(chunk)
    raw = bytes(chunks)
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    signature = request.headers.get("x-razorpay-signature", "")
    if not re.fullmatch(r"[0-9a-f]{64}", signature) or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid webhook signature.")
    try:
        data = json.loads(raw)
        if data.get("event") != "payment_link.paid":
            return {"accepted": True, "ignored": True}
        entity = data["payload"]["payment_link"]["entity"]
        if not isinstance(entity, dict):
            raise ValueError()
        cart = await session.scalar(select(ShoppingCart).where(ShoppingCart.checkout_id == entity["id"])
            .with_for_update().execution_options(populate_existing=True))
        if cart is None or entity.get("currency") != "INR" or entity.get("amount") != cart.total_paise or entity.get("amount_paid") != cart.total_paise or entity.get("reference_id") != cart.id or entity.get("status") != "paid":
            raise HTTPException(422, "Webhook does not match a test checkout.")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(422, "Malformed payment webhook.") from None
    if cart.status == "test_paid":
        return {"accepted": True, "duplicate": True}
    if cart.status != "checkout_ready":
        raise HTTPException(409, "Checkout is not ready for settlement.")
    await carts.transition(session, cart, "checkout_ready", "test_paid")
    await ledger.append(session, cart, "test_payment_verified", {"provider_id": cart.checkout_id, "amount_paise": cart.total_paise})
    await session.commit()
    return {"accepted": True}
