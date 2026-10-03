"""Thin Master Orchestrator: read, route, collect, validate, coordinate."""
import logging
from collections.abc import Callable
from datetime import datetime
from dataclasses import replace
from sqlalchemy import select
from app.models.product import Product
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.agents.listing_agent import ListingAgent
from app.schemas.listing import ListingRecommendation
from app.services.listing.signals import ListingSignals
from app.services.listing.generator import generate_listing_recommendation
from app.schemas.listing import ListingPolicy
from app.agents.promotion_agent import PromotionAgent
from app.schemas.promotion import PromotionRecommendation, PromotionPolicy
from app.services.promotion.signals import PromotionSignals
from app.agents.pricing_agent import PricingAgent
from app.agents.restock_agent import RestockAgent
from app.schemas.orchestration import ActionPlan, AgentError, AgentName, AgentResult, OrchestrationRequest
from app.schemas.pricing import PricingRecommendation, RiskLevel
from app.schemas.restock import RestockPolicy, RestockRecommendation
from app.services.pricing.signals import ProductPricingSignals
from app.services.restock.signals import restock_signals_from_snapshot
from app.services.orchestration.context import build_context
from app.services.orchestration.routing import select_agents
from app.services.orchestration.coordinator import create_plan
from app.services.orchestration.strategy import INTELLIGENT_GOALS, detect_opportunity
from app.services.orchestration.intelligence import coordinate

Recommendation = PricingRecommendation | RestockRecommendation | PromotionRecommendation | ListingRecommendation
SnapshotAgent = Callable[[ProductPricingSignals | PromotionSignals | ListingSignals], Recommendation]
logger = logging.getLogger(__name__)


def default_agents(request: OrchestrationRequest) -> dict[AgentName, SnapshotAgent]:
    limits = request.constraints
    pricing = PricingAgent(max_increase_percent=limits.max_price_increase_percent,
                           max_decrease_percent=limits.max_price_decrease_percent)
    restock = RestockAgent(RestockPolicy(max_reorder_quantity=limits.max_reorder_quantity))
    promotion = PromotionAgent(PromotionPolicy(max_discount_percent=limits.max_promotion_discount_percent))
    return {AgentName.LISTING: ListingAgent().recommend, AgentName.PROMOTION: promotion.recommend, AgentName.PRICING: pricing.recommend,
            AgentName.RESTOCK: lambda signals: restock.recommend(restock_signals_from_snapshot(signals))}


def validate_agent_output(
    name: AgentName, rec: Recommendation, request: OrchestrationRequest, snapshot: ProductPricingSignals | PromotionSignals | ListingSignals,
) -> None:
    """Validate returned types and merchant constraints before coordination."""
    if name == AgentName.LISTING:
        if not isinstance(rec, ListingRecommendation) or not isinstance(snapshot, ListingSignals):
            raise ValueError("Unexpected listing output.")
        validated = ListingRecommendation.model_validate(rec.model_dump())
        expected = generate_listing_recommendation(snapshot, ListingPolicy())
        if validated != expected:
            raise ValueError("Listing output is not grounded in the supplied product snapshot.")
        return
    if name == AgentName.PROMOTION:
        if not isinstance(rec, PromotionRecommendation) or not isinstance(snapshot, PromotionSignals):
            raise ValueError("Unexpected promotion output.")
        rec = PromotionRecommendation.model_validate(rec.model_dump())
        p = snapshot.product
        if rec.current_price != p.current_price or rec.cost_price != p.cost_price or rec.available_inventory != snapshot.restock.available_inventory:
            raise ValueError("Promotion output does not match its snapshot.")
        if rec.discount_percentage > Decimal(str(request.constraints.max_promotion_discount_percent)):
            raise ValueError("Promotion exceeds merchant discount policy.")
        if rec.promotion_recommended:
            floor = p.cost_price / (1 - Decimal(str(settings.PROMOTION_MIN_MARGIN_PERCENT)) / 100)
            if rec.promotional_price < floor or snapshot.restock.risk_level == RiskLevel.HIGH or snapshot.restock.available_inventory <= p.reorder_point:
                raise ValueError("Promotion violates margin or inventory protection.")
        return
    if name == AgentName.PRICING:
        if not isinstance(rec, PricingRecommendation):
            raise ValueError("Unexpected pricing output.")
        if rec.current_price != snapshot.current_price or rec.cost_price != snapshot.cost_price:
            raise ValueError("Pricing output does not match the business snapshot.")
        if not rec.recommended_price.is_finite():
            raise ValueError("Pricing output must be finite.")
        minimum = snapshot.cost_price * (1 + Decimal(str(settings.MIN_MARGIN_PERCENT)) / 100)
        if rec.recommended_price < minimum:
            raise ValueError("Pricing output violates configured cost floor.")
        limits = request.constraints
        upper = rec.current_price * (1 + Decimal(str(limits.max_price_increase_percent)) / 100)
        lower = rec.current_price * (1 - Decimal(str(limits.max_price_decrease_percent)) / 100)
        if not lower <= rec.recommended_price <= upper:
            raise ValueError("Pricing proposal exceeds merchant constraints.")
    elif not isinstance(rec, RestockRecommendation) or rec.recommended_quantity > request.constraints.max_reorder_quantity:
        raise ValueError("Restock proposal exceeds merchant constraints.")
    elif rec.current_inventory != snapshot.total_quantity or rec.available_inventory != snapshot.available_quantity:
        raise ValueError("Restock output does not match the business snapshot.")


class MasterOrchestrator:
    """Coordinate snapshot-based specialist recommendations without execution."""
    def __init__(self, agents: dict[AgentName, SnapshotAgent] | None = None) -> None:
        self.agents = agents

    async def analyze(
        self, request: OrchestrationRequest, session: AsyncSession,
        as_of: datetime | None = None,
    ) -> ActionPlan:
        intelligent = request.goal in INTELLIGENT_GOALS
        scope_has_more = False
        if intelligent and request.product_ids is None:
            with session.no_autoflush:
                ids = (await session.execute(select(Product.id).where(
                    Product.merchant_id == request.merchant_id, Product.status == "active")
                    .order_by(Product.id).limit(request.limit + 1))).scalars().all()
            scope_has_more = len(ids) > request.limit
            request = request.model_copy(update={"product_ids": list(ids[:request.limit])})
        selected = tuple(AgentName) if intelligent else select_agents(request.goal)
        context = await build_context(request, selected, session, as_of)
        opportunities = [detect_opportunity(product, request.goal) for product in context.products] if intelligent else []
        selections = {item.product_id: item.selected_agents for item in opportunities}
        registry = self.agents if self.agents is not None else default_agents(request)
        results = []
        # Sequential pure calculations: never share an AsyncSession across concurrent tasks.
        for product in context.products:
            for name in selections.get(product.product_id, selected):
                try:
                    rec = registry[name](product.signals[name])
                except ValueError:
                    error = AgentError(code="invalid_agent_input", message="Agent could not safely analyze the product's input data.")
                    results.append(AgentResult(agent_name=name, product_id=product.product_id, success=False, error=error))
                    continue
                except Exception:
                    logger.warning("Agent %s failed for product %d", name, product.product_id)
                    error = AgentError(code="agent_failed", message="Agent analysis failed; review the product before taking action.")
                    results.append(AgentResult(agent_name=name, product_id=product.product_id, success=False, error=error))
                    continue
                try:
                    validate_agent_output(name, rec, request, product.signals[name])
                    result = AgentResult(agent_name=name, product_id=product.product_id, success=True,
                                         recommendation=rec, risk_level=rec.risk_level, confidence=rec.confidence)
                except (ValueError, AttributeError):
                    result = AgentResult(agent_name=name, product_id=product.product_id, success=False,
                        error=AgentError(code="invalid_agent_output", message="Agent output failed product or safety validation."))
                results.append(result)
        if intelligent:
            chosen = tuple(name for name in AgentName if any(name in agents for agents in selections.values()))
            context = replace(context, selected_agents=chosen)
        base = create_plan(context, results)
        return coordinate(base, opportunities, scope_has_more) if intelligent else base
