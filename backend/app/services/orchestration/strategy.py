"""Central, deterministic goal weights and opportunity-based specialist selection."""
from app.core.config import settings
from app.schemas.orchestration import AgentName, Goal, ProductOpportunity
from app.schemas.listing import ListingPolicy
from app.services.listing.quality import analyze_quality
from app.services.pricing.signals import ProductPricingSignals
from app.services.restock.calculator import calculate_restock_recommendation
from app.services.restock.signals import restock_signals_from_snapshot
from app.services.orchestration.context import ProductContext

# inventory health, revenue, margin, catalog quality; heuristic importance, not uplift.
GOAL_WEIGHTS = {
    Goal.BALANCED: (.30, .30, .20, .20),
    Goal.MAXIMIZE_REVENUE: (.20, .45, .20, .15),
    Goal.STOCKOUT_PREVENTION: (.60, .15, .15, .10),
    Goal.EXCESS_REDUCTION: (.20, .45, .10, .25),
    Goal.PERFORMANCE: (.20, .30, .15, .35),
    Goal.CATALOG: (.10, .10, .10, .70),
}
INTELLIGENT_GOALS = frozenset(GOAL_WEIGHTS)


def detect_opportunity(product: ProductContext, goal: Goal) -> ProductOpportunity:
    p: ProductPricingSignals = product.signals[AgentName.PRICING]
    stock_risk = not p.has_inventory
    restock_needed = stock_risk
    try:
        stock = calculate_restock_recommendation(restock_signals_from_snapshot(product.signals[AgentName.RESTOCK]))
        stock_risk = stock_risk or stock.risk_level == 'high' or stock.stockout_risk
        restock_needed = stock_risk or stock.recommended_quantity > 0
    except ValueError:
        stock_risk = restock_needed = True
    quality = None
    listing_issue = True
    try:
        quality = analyze_quality(product.signals[AgentName.LISTING], ListingPolicy())
        listing_issue = bool(quality.issues)
    except ValueError:
        pass
    pricing = p.status == 'active' and p.has_sufficient_data and (
        p.is_strong_sales and (p.is_low_stock or p.is_healthy_inventory) or p.is_weak_sales and p.is_high_inventory)
    excess = p.status == 'active' and p.has_inventory and p.is_high_inventory and p.sales_velocity < settings.SLOW_SALES_THRESHOLD
    reasons = {}
    def select(name: AgentName, reason: str) -> None:
        reasons[name] = reason
    if goal == Goal.BALANCED:
        for name in AgentName:
            select(name, 'Balanced growth requests broad analysis of revenue, inventory, margin and catalog quality.')
    else:
        if restock_needed:
            select(AgentName.RESTOCK, 'Current inventory exposure requires replenishment or verification; safety overrides the goal.')
        if goal == Goal.STOCKOUT_PREVENTION:
            if not reasons:
                select(AgentName.RESTOCK, 'Verify inventory coverage for the stockout-prevention goal.')
        elif goal == Goal.CATALOG:
            if listing_issue:
                select(AgentName.LISTING, 'Catalog quality goal and current text issues require grounded listing review.')
        else:
            if pricing or excess:
                select(AgentName.PRICING, 'Current demand and inventory show a bounded pricing opportunity aligned with the goal.')
            if excess and not stock_risk:
                select(AgentName.PROMOTION, 'Excess available inventory and slow sales warrant a controlled promotion assessment.')
            if listing_issue:
                select(AgentName.LISTING, 'Listing issues may constrain product performance; review factual content.')
    return ProductOpportunity(product_id=p.product_id, product_name=p.name,
        pricing_opportunity=pricing, stockout_risk=stock_risk, excess_inventory=excess,
        listing_issue=listing_issue, listing_quality=quality.score if quality else None,
        inventory_known=p.has_inventory, active=p.status == "active", selected_agents=list(reasons), selection_reasons=reasons)


def goal_score(goal: Goal, agent: AgentName, strength: float, confidence: float) -> float:
    inventory, revenue, margin, catalog = GOAL_WEIGHTS[goal]
    weight = {AgentName.RESTOCK: inventory, AgentName.PRICING: revenue + margin,
              AgentName.PROMOTION: revenue, AgentName.LISTING: catalog + (.5 * revenue if strength == 1 else 0)}[agent]
    return round(weight * min(1, max(0, strength)) * confidence, 4)
