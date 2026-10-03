"""Revalidate immutable approved proposals against current merchant state."""
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.product import Product
from app.schemas.actions import ActionPayload, PricePayload, RestockPayload, PromotionPayload, ListingPayload, PolicyValidationResult
from app.agents.restock_agent import RestockAgent
from app.agents.promotion_agent import PromotionAgent
from app.agents.listing_agent import ListingAgent
from app.services.pricing.rules import apply_below_cost_guardrail, apply_price_change_caps


async def validate_policy(payload: ActionPayload, product: Product, session: AsyncSession,
                          risk: str = "high") -> PolicyValidationResult:
    violations: list[str] = []
    if product.status != "active":
        violations.append("Product is not active.")
    if isinstance(payload, (PricePayload, PromotionPayload)) and product.cost_price is None:
        return PolicyValidationResult(is_valid=False, policy_name=f"{payload.kind}_policy",
            violations=["Cost price is unknown; margin-dependent execution is blocked."], risk_level="high")
    try:
        if isinstance(payload, PricePayload):
            if product.selling_price != payload.old_price or product.cost_price != payload.expected_cost:
                violations.append("Stale price or cost: current product values changed.")
            floor, clamped = apply_below_cost_guardrail(payload.new_price, product.cost_price, settings.MIN_MARGIN_PERCENT)
            if clamped or floor != payload.new_price:
                violations.append("New price violates the configured cost/margin floor.")
            capped, up, down = apply_price_change_caps(product.selling_price, payload.new_price, settings.MAX_PRICE_INCREASE_PERCENT, settings.MAX_PRICE_DECREASE_PERCENT)
            if up or down or capped != payload.new_price:
                violations.append("Price change exceeds configured maximum change.")
            if payload.new_price < payload.old_price:
                stock = await RestockAgent().analyze(product.id, session)
                if stock.risk_level == "high" or stock.stockout_risk or stock.available_inventory <= stock.reorder_point:
                    violations.append("Current inventory risk blocks a demand-stimulating price reduction.")
            if payload.new_price == payload.old_price:
                violations.append("Price hold has no change to execute.")
        elif isinstance(payload, RestockPayload):
            if payload.quantity > settings.MAX_REORDER_QUANTITY:
                violations.append("Restock quantity exceeds configured maximum.")
            fresh = await RestockAgent().analyze(product.id, session)
            if fresh.recommended_quantity <= 0 or payload.quantity > fresh.recommended_quantity:
                violations.append("Restock request is no longer relevant to current replenishment need.")
        elif isinstance(payload, PromotionPayload):
            if product.selling_price != payload.old_price or product.cost_price != payload.expected_cost:
                violations.append("Stale price or cost: current product values changed.")
            if payload.discount_percentage > Decimal(str(settings.MAX_PROMOTION_DISCOUNT_PERCENT)):
                violations.append("Discount exceeds configured maximum.")
            expected = (payload.old_price * (1 - payload.discount_percentage / 100)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            floor = product.cost_price / (1 - Decimal(str(settings.PROMOTION_MIN_MARGIN_PERCENT)) / 100)
            if payload.promotional_price != expected or payload.promotional_price < floor:
                violations.append("Promotion price violates discount arithmetic or retained gross margin.")
            stock = await RestockAgent().analyze(product.id, session)
            if stock.risk_level == "high" or stock.available_inventory <= stock.reorder_point or stock.stockout_risk:
                violations.append("Current stockout risk or low inventory blocks promotion.")
            fresh = await PromotionAgent().analyze(product.id, session, merchant_id=product.merchant_id)
            if not fresh.promotion_recommended:
                violations.append("Promotion is no longer relevant under current demand and inventory signals.")
        elif isinstance(payload, ListingPayload):
            if (product.name, product.description, product.category, product.sku) != (payload.old_title, payload.old_description, payload.expected_category, payload.expected_sku):
                violations.append("Stale listing: source content or identifiers changed.")
            fresh = await ListingAgent().analyze(product.id, session, product.merchant_id)
            if (payload.new_title, payload.new_description) != (fresh.recommended_title, fresh.recommended_description):
                violations.append("Listing content is not grounded in current product data.")
            if (payload.new_title, payload.new_description) == (product.name, product.description):
                violations.append("Listing has no content change to execute.")
    except ValueError:
        violations.append("Current product data cannot pass agent input or safety validation.")
    return PolicyValidationResult(is_valid=not violations, policy_name=f"{payload.kind}_policy",
        violations=violations, risk_level="high" if violations else risk,
        warnings=["Local/mock execution only; human approval and separate execution are required."])
