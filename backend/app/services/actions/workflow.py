"""Human approvals and local execution are separate transactional application tools."""
import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pydantic import TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.action import Action, ActionStatus
from app.models.approval import Approval
from app.models.audit_log import AuditLog
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.merchant import Merchant
from app.models.recommendation import Recommendation
from app.models.price_history import PriceHistory
from app.schemas.actions import (ActionCreate, ActionDecision, ActionPayload, ActionResponse, ActionType,
    PolicyValidationResult, PricePayload, RestockPayload, PromotionPayload, ListingPayload)
from app.schemas.pricing import PricingRecommendation
from app.schemas.restock import RestockRecommendation
from app.schemas.promotion import PromotionRecommendation
from app.schemas.listing import ListingRecommendation
from app.services.policies.validator import validate_policy
from app.services.actions.state import ActionError, transition

logger = logging.getLogger(__name__)
SCHEMAS = {"pricing": PricingRecommendation, "restock": RestockRecommendation,
           "promotion": PromotionRecommendation, "listing": ListingRecommendation}
PAYLOAD = TypeAdapter(ActionPayload)


def audit(session: AsyncSession, action: Action, rec: Recommendation, event: str,
          actor: str, details: dict | None = None) -> None:
    session.add(AuditLog(merchant_id=rec.merchant_id, entity_type="action", entity_id=str(action.id),
        event_type=event, message=event.replace("_", " ").capitalize(),
        metadata_={"action_id": action.id, "product_id": rec.product_id, "agent": rec.recommendation_type,
                   "status": action.status, "performed_by": actor, **(details or {})}))
    logger.info("action_event event=%s action_id=%s merchant_id=%s", event, action.id, rec.merchant_id)


async def product_for(session: AsyncSession, product_id: int, merchant_id: int, lock: bool = False) -> Product:
    query = select(Product).where(Product.id == product_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    product = await session.scalar(query)
    if product is None:
        raise ActionError(404, "Product not found.")
    if product.merchant_id != merchant_id:
        raise ActionError(403, "Product does not belong to the merchant.")
    if lock:
        # Stable stock snapshot while inventory-sensitive execution is validated.
        await session.scalar(select(Inventory).where(Inventory.product_id == product_id).with_for_update().execution_options(populate_existing=True))
    return product


def make_payload(rec, product: Product) -> ActionPayload:
    if isinstance(rec, PricingRecommendation):
        return PricePayload(product_id=rec.product_id, old_price=rec.current_price,
                            new_price=rec.recommended_price, expected_cost=rec.cost_price)
    if isinstance(rec, RestockRecommendation):
        return RestockPayload(product_id=rec.product_id, quantity=rec.recommended_quantity)
    if isinstance(rec, PromotionRecommendation):
        if not rec.promotion_recommended:
            raise ValueError("No promotion is recommended.")
        return PromotionPayload(product_id=rec.product_id, old_price=rec.current_price,
            expected_cost=rec.cost_price, discount_percentage=rec.discount_percentage, promotional_price=rec.promotional_price)
    if isinstance(rec, ListingRecommendation):
        return ListingPayload(product_id=rec.product_id, old_title=rec.current_title,
            old_description=rec.current_description, expected_category=product.category, expected_sku=product.sku,
            new_title=rec.recommended_title, new_description=rec.recommended_description)
    raise ValueError("Unsupported recommendation type.")


async def load_action(session: AsyncSession, action_id: int, merchant_id: int, lock: bool = False):
    query = select(Action).where(Action.id == action_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    action = await session.scalar(query)
    if action is None:
        raise ActionError(404, "Action not found.")
    rec = await session.get(Recommendation, action.recommendation_id, populate_existing=True)
    if rec is None or rec.merchant_id != merchant_id:
        raise ActionError(403, "Action does not belong to the merchant.")
    if not action.workflow_key or not action.result or not action.result.get("approval_id"):
        raise ActionError(409, "Legacy action must be reviewed through the guarded workflow; it cannot execute.")
    approval = await session.get(Approval, action.result["approval_id"], populate_existing=True)
    if approval is None or approval.recommendation_id != rec.id:
        raise ActionError(409, "Approval record does not match this action.")
    return action, rec, approval


async def response_for(session: AsyncSession, action: Action, rec: Recommendation, approval: Approval) -> ActionResponse:
    product = await product_for(session, rec.product_id, rec.merchant_id)
    payload = PAYLOAD.validate_python(action.payload)
    return ActionResponse(id=action.id, recommendation_id=rec.id, merchant_id=rec.merchant_id,
        product_id=product.id, product_name=product.name, agent=rec.recommendation_type, reason=rec.description or "Review proposal",
        action_type=action.action_type, payload=payload, status=action.status, risk_level=action.risk_level,
        execution_mode="local_mutation" if payload.kind in ("price_change", "listing_update") else "simulated",
        created_at=action.created_at, executed_at=action.executed_at,
        approved_by=approval.approved_by if approval.status != "pending" else None,
        approval_status=approval.status, comment=approval.comment,
        policy=PolicyValidationResult.model_validate(action.result["policy"]), result=action.result.get("execution"))


async def create_action(session: AsyncSession, request: ActionCreate) -> ActionResponse:
    key = ""
    try:
        if await session.get(Merchant, request.merchant_id) is None:
            raise ActionError(404, "Merchant not found.")
        if request.recommendation_id:
            rec = await session.scalar(select(Recommendation).where(Recommendation.id == request.recommendation_id).with_for_update())
            if rec is None:
                raise ActionError(404, "Recommendation not found.")
            if rec.merchant_id != request.merchant_id:
                raise ActionError(403, "Recommendation does not belong to the merchant.")
            agent = rec.recommendation_type
            if agent not in SCHEMAS:
                raise ActionError(422, "Unsupported recommendation type.")
            value = SCHEMAS[agent].model_validate(rec.recommended_value)
            key = f"recommendation:{rec.id}"
        else:
            agent = request.agent
            if not isinstance(request.recommendation, SCHEMAS[agent]):
                raise ActionError(422, "Agent and recommendation type must match.")
            value = SCHEMAS[agent].model_validate(request.recommendation.model_dump())
            canonical = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            key = hashlib.sha256(f"{request.merchant_id}:{agent}:{canonical}".encode()).hexdigest()
            rec = None
        existing_query = select(Action).where(Action.workflow_key == key)
        if rec is not None:
            existing_query = select(Action).where(Action.recommendation_id == rec.id, Action.workflow_key.is_not(None))
        existing = await session.scalar(existing_query)
        if existing:
            return await response_for(session, *await load_action(session, existing.id, request.merchant_id))
        if rec is not None and (rec.status != "pending" or rec.product_id != value.product_id):
            raise ActionError(409, "Saved recommendation is not pending or does not match its product.")
        product = await product_for(session, value.product_id, request.merchant_id, lock=True)
        payload = make_payload(value, product)
        policy = await validate_policy(payload, product, session, value.risk_level)
        if rec is None:
            rec = Recommendation(merchant_id=request.merchant_id, product_id=value.product_id,
                recommendation_type=agent, title=f"{agent.capitalize()} action review", description=value.reason,
                recommended_value=value.model_dump(mode="json"), confidence=value.confidence, status="pending")
            session.add(rec)
            await session.flush()
        action = Action(recommendation_id=rec.id, action_type=payload.kind, payload=payload.model_dump(mode="json"),
            status="pending", risk_level=policy.risk_level, workflow_key=key)
        session.add(action)
        await session.flush()
        approval = Approval(recommendation_id=rec.id, approved_by="unassigned", status="pending")
        session.add(approval)
        await session.flush()
        action.result = {"policy": policy.model_dump(mode="json"), "approval_id": approval.id}
        audit(session, action, rec, "recommendation_created" if not request.recommendation_id else "recommendation_selected", "development-merchant")
        audit(session, action, rec, "action_created", "development-merchant")
        audit(session, action, rec, "policy_validated", "system", {"policy": policy.model_dump(mode="json")})
        if policy.is_valid:
            transition(action, ActionStatus.VALIDATED)
            audit(session, action, rec, "action_validated", "system")
            transition(action, ActionStatus.AWAITING_APPROVAL)
            audit(session, action, rec, "action_awaiting_approval", "system")
        else:
            # Blocked creation is terminal, never transformed to different user-approved values.
            transition(action, ActionStatus.FAILED)
            action.result = {**action.result, "execution": {"outcome": "blocked", "violations": policy.violations}}
            audit(session, action, rec, "execution_blocked", "system", {"violations": policy.violations})
        await session.commit()
        return await response_for(session, action, rec, approval)
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(select(Action).where(Action.workflow_key == key))
        if existing:
            return await response_for(session, *await load_action(session, existing.id, request.merchant_id))
        raise
    except Exception:
        await session.rollback()
        raise


async def decide_action(session: AsyncSession, action_id: int, decision: ActionDecision, approved: bool) -> ActionResponse:
    try:
        action, rec, approval = await load_action(session, action_id, decision.merchant_id, lock=True)
        target = ActionStatus.APPROVED if approved else ActionStatus.REJECTED
        # Compare-and-set also protects engines where SELECT FOR UPDATE is unsupported.
        claimed = await session.execute(update(Action).where(Action.id == action_id, Action.status == "awaiting_approval")
            .values(status=target.value).execution_options(synchronize_session=False))
        if claimed.rowcount != 1:
            raise ActionError(409, "Action was already reviewed by another request.")
        transition(action, target)
        approval.status = target.value
        approval.approved_by = decision.actor
        approval.comment = decision.comment
        rec.status = target.value
        audit(session, action, rec, "action_approved" if approved else "action_rejected", decision.actor, {"comment": decision.comment})
        await session.commit()
        return await response_for(session, action, rec, approval)
    except Exception:
        await session.rollback()
        raise


async def apply_local(session: AsyncSession, payload: ActionPayload, product: Product, reason: str) -> dict:
    """Only this executor may mutate local fields; simulated requests never add stock or change base price."""
    if isinstance(payload, PricePayload):
        result = await session.execute(update(Product).where(Product.id == product.id,
            Product.selling_price == payload.old_price, Product.cost_price == payload.expected_cost)
            .values(selling_price=payload.new_price).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise ActionError(409, "Product price changed during execution.")
        session.add(PriceHistory(product_id=product.id, old_price=payload.old_price, new_price=payload.new_price, reason=reason))
        return {"outcome": "executed", "mode": "local_mutation", "before": {"selling_price": str(payload.old_price.quantize(Decimal(".01")))}, "after": {"selling_price": str(payload.new_price.quantize(Decimal(".01")))}}
    if isinstance(payload, ListingPayload):
        result = await session.execute(update(Product).where(Product.id == product.id, Product.name == payload.old_title,
            Product.description == payload.old_description, Product.category == payload.expected_category, Product.sku == payload.expected_sku)
            .values(name=payload.new_title, description=payload.new_description).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise ActionError(409, "Product listing changed during execution.")
        return {"outcome": "executed", "mode": "local_mutation", "before": {"title": payload.old_title, "description": payload.old_description}, "after": {"title": payload.new_title, "description": payload.new_description}}
    return {"outcome": "executed", "mode": "simulated", "requested": payload.model_dump(mode="json"),
            "message": "Simulated replenishment request recorded; inventory has not arrived." if isinstance(payload, RestockPayload) else "Simulated promotion activation recorded; base selling price is unchanged."}


async def execute_action(session: AsyncSession, action_id: int, decision: ActionDecision) -> ActionResponse:
    try:
        action, rec, approval = await load_action(session, action_id, decision.merchant_id, lock=True)
        if action.status == "executed":
            return await response_for(session, action, rec, approval)
        if action.status != "approved" or approval.status != "approved" or rec.status != "approved":
            audit(session, action, rec, "execution_blocked", decision.actor, {"violations": ["Approved action and matching human approval are required."]})
            await session.commit()
            raise ActionError(409, "Execution requires an approved action and matching human approval.")
        product = await product_for(session, rec.product_id, rec.merchant_id, lock=True)
        payload = PAYLOAD.validate_python(action.payload)
        # Stored payload must still match the originally reviewed recommendation.
        original = SCHEMAS[rec.recommendation_type].model_validate(rec.recommended_value)
        if original.product_id != rec.product_id or action.action_type != payload.kind or payload != make_payload(original, product):
            policy = PolicyValidationResult(is_valid=False, policy_name=f"{payload.kind}_policy", violations=["Action payload does not match the reviewed recommendation."], risk_level="high")
        else:
            policy = await validate_policy(payload, product, session, action.risk_level)
        audit(session, action, rec, "policy_validated", "system", {"policy": policy.model_dump(mode="json")})
        previous = action.result
        if not policy.is_valid:
            action.risk_level = "high"
            audit(session, action, rec, "execution_blocked", decision.actor, {"violations": policy.violations})
            action.result = {**previous, "policy": policy.model_dump(mode="json"), "execution": {"outcome": "blocked", "violations": policy.violations}}
            await session.commit()
            return await response_for(session, action, rec, approval)
        claimed = await session.execute(update(Action).where(Action.id == action_id, Action.status == "approved")
            .values(status="executing").execution_options(synchronize_session=False))
        if claimed.rowcount != 1:
            raise ActionError(409, "Action execution was already claimed.")
        transition(action, ActionStatus.EXECUTING)
        audit(session, action, rec, "execution_started", decision.actor)
        await session.flush()
        try:
            async with session.begin_nested():
                result = await apply_local(session, payload, product, rec.description or "Approved local action")
                transition(action, ActionStatus.EXECUTED)
                action.executed_at = datetime.now(timezone.utc)
                rec.status = "executed"
                action.result = {**previous, "policy": policy.model_dump(mode="json"), "execution": result}
                audit(session, action, rec, "execution_completed", decision.actor, result)
                await session.flush()
        except Exception:
            # Savepoint rolls back product/history/result mutations together, then records a safe failure.
            await session.refresh(action)
            await session.refresh(rec)
            transition(action, ActionStatus.FAILED)
            action.result = {**previous, "policy": policy.model_dump(mode="json"), "execution": {"outcome": "failed", "message": "Local execution failed and its changes were rolled back."}}
            audit(session, action, rec, "execution_failed", decision.actor)
            logger.warning("local_execution_failed action_id=%s", action_id)
        await session.commit()
        return await response_for(session, action, rec, approval)
    except Exception:
        await session.rollback()
        raise
