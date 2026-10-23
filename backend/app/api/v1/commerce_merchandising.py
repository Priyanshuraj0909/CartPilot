"""Account-scoped growth rules, audit dashboards and discovery previews."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_database_session
from app.api.v1.accounts import current_account
from app.api.v1.commerce import public_limit
from app.models.account import Account
from app.models.commerce import ShoppingCart
from app.models.commerce import CommerceEvent
from app.schemas.commerce import Confirmation, SearchRequest
from app.schemas.commerce_workflows import RulesRequest, ProviderImport, ResolutionRequest, ReturnReview
from app.services.commerce import carts, ledger, merchandising
from app.services.commerce import onboarding
from app.services.commerce import resolution
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/commerce/merchant", tags=["Commerce merchandising"])


@router.post("/returns/{operation_id}/review")
async def review_return(operation_id: str, body: ReturnReview, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    from app.models.commerce_workflows import CommerceOperation
    operation = await session.scalar(select(CommerceOperation).join(ShoppingCart, ShoppingCart.id == CommerceOperation.cart_id)
        .where(CommerceOperation.id == operation_id, ShoppingCart.merchant_id == account.merchant_id,
            CommerceOperation.kind == "return_review"))
    if operation is None:
        raise HTTPException(404, "Return review not found.")
    cart = await session.get(ShoppingCart, operation.cart_id, with_for_update=True)
    operation = await session.get(CommerceOperation, operation.id, populate_existing=True, with_for_update=True)
    target = {"approve": "approved", "reject": "rejected", "received": "received"}[body.decision]
    if operation.status == target:
        return resolution.projection(operation)
    if (operation.status, target) not in {("review_required", "approved"), ("review_required", "rejected"), ("approved", "received")}:
        raise HTTPException(409, "Return review transition is not permitted.")
    operation.status = target
    await ledger.append(session, cart, "return_review_" + target, {"operation_id": operation.id, "automatic_refund": False, "physical_stock_changed": False})
    await session.commit()
    return resolution.projection(operation)


@router.post("/carts/{cart_id}/resolution")
async def owner_resolution(cart_id: str, body: ResolutionRequest, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    from app.models.commerce import ShopperSession
    from app.api.v1.commerce_workflows import create_handoff
    cart = await session.scalar(select(ShoppingCart).where(ShoppingCart.id == cart_id,
        ShoppingCart.merchant_id == account.merchant_id).with_for_update())
    if cart is None:
        raise HTTPException(404, "Cart not found.")
    identity = await session.get(ShopperSession, cart.shopper_hash)
    result = await resolution.execute(session, identity, cart, body)
    if body.action == "recover" and result.get("details", {}).get("recovered_cart_id"):
        handoff = await create_handoff(result["details"]["recovered_cart_id"], Confirmation(confirm=True), identity, session)
        return {**result, "review_path": handoff["path"]}
    return result


@router.get("/attribution")
async def attribution(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    rows = (await session.execute(select(CommerceEvent, ShoppingCart.status).join(ShoppingCart,
        ShoppingCart.id == CommerceEvent.cart_id).where(ShoppingCart.merchant_id == account.merchant_id,
        CommerceEvent.event.in_(["upsell_accepted", "recovery_offer_accepted"]))
        .order_by(CommerceEvent.id.desc()).limit(1000))).all()
    return {"recorded_upsell_acceptances": sum(e.event == "upsell_accepted" for e, _ in rows),
        "recorded_recovery_acceptances": sum(e.event == "recovery_offer_accepted" for e, _ in rows),
        "test_paid_upsell_value_paise": sum(e.payload.get("value_paise", 0) for e, status in rows
            if e.event == "upsell_accepted" and status == "test_paid"),
        "real_incremental_revenue_paise": None,
        "interpretation": "Recorded selections and test payment value only. Causal AI revenue attribution requires a controlled experiment."}


@router.post("/catalog/provider", dependencies=[Depends(public_limit)])
async def import_api(body: ProviderImport, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    try:
        return await onboarding.import_provider(session, account.merchant_id, body.source)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Concurrent import detected. Refresh catalog before retrying.") from None


@router.post("/catalog/demo")
async def demo(body: Confirmation, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    try:
        return await onboarding.seed_demo(session, account.merchant_id)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Demo catalog already exists.") from None


@router.post("/catalog/archive")
async def archive_catalog(body: Confirmation, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    from app.models.product import Product
    from sqlalchemy import update
    result = await session.execute(update(Product).where(Product.merchant_id == account.merchant_id,
        Product.source == "local", Product.status == "active").values(status="archived"))
    await session.commit()
    return {"archived": result.rowcount, "history_preserved": True}


@router.get("/rules", response_model=RulesRequest)
async def get_rules(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    return RulesRequest.model_validate(await merchandising.rules_for(session, account.merchant_id), from_attributes=True)


@router.put("/rules", response_model=RulesRequest)
async def put_rules(body: RulesRequest, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    products, _ = await merchandising.catalog(session, account.merchant_id)
    categories = {p.category.casefold() for p in products}
    referenced = {r.category.casefold() for r in body.growth_rules} | {p.category_a for p in body.compatibility} | {p.category_b for p in body.compatibility}
    if referenced - categories:
        raise HTTPException(422, "Rules must reference categories in this store's current catalog.")
    await merchandising.save_rules(session, account.merchant_id, body)
    return body


@router.post("/compatibility/generate", dependencies=[Depends(public_limit)])
async def generate(body: Confirmation, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    return await merchandising.generate_compatibility(session, account.merchant_id)


@router.get("/context")
async def context(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    result = await merchandising.contextual_snapshot()
    rules = await merchandising.rules_for(session, account.merchant_id)
    import time
    now = int(time.time())
    result["events"] = [{"name": r.get("campaign_name") or r["id"], "category": r["category"],
        "starts_at": r.get("starts_at"), "ends_at": r.get("ends_at")} for r in rules.growth_rules
        if r.get("enabled") and r.get("starts_at") is not None and now <= r["starts_at"] <= now + 30 * 86400]
    return result


@router.get("/opportunities")
async def opportunities(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    return {"opportunities": await merchandising.opportunities(session, account.merchant_id)}


@router.post("/growth-cycle", dependencies=[Depends(public_limit)])
async def cycle(body: Confirmation, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    return await merchandising.run_cycle(session, account.merchant_id)


@router.get("/scheduler")
async def scheduler(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    rules = await merchandising.rules_for(session, account.merchant_id)
    return {"enabled": rules.scheduler_enabled, "interval_seconds": rules.interval_seconds,
        "next_run_at": rules.next_run_at, "last_result": rules.last_result,
        "requires_persistent_worker": True}


@router.post("/ranking-preview", dependencies=[Depends(public_limit)])
async def ranking_preview(body: SearchRequest, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    return await merchandising.preview(session, account.merchant_id, body.query, body.budget_paise or 10000000, body.anchor_product_id)


@router.get("/lift")
async def lift(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    return {"pairs": await merchandising.purchase_lift(session, account.merchant_id),
        "interpretation": "Observed completed-order associations, not causal incremental revenue."}


@router.get("/audit")
async def audit_dashboard(account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    rows = (await session.scalars(select(ShoppingCart).where(ShoppingCart.merchant_id == account.merchant_id)
        .order_by(ShoppingCart.created_at.desc(), ShoppingCart.id).limit(100))).all()
    results = []
    for cart in rows:
        events = await ledger.events(session, cart.id)
        state = await resolution.eligibility(session, cart)
        results.append({"cart": carts.response(cart), "valid": ledger.verify(events), "operations": state["operations"],
            "events": [{"sequence": e.sequence, "event": e.event, "payload": e.payload, "created_at": e.created_at, "digest": e.digest} for e in events]})
    return {"carts": results, "bounded_to": 100, "real_revenue_paise": 0}
