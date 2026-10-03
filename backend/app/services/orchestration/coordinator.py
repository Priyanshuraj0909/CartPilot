"""Priority, final advisory actions, risk aggregation, and plan summary."""
from app.schemas.orchestration import ActionPlan, AgentName, AgentResult, PlanRecommendation, Priority
from app.schemas.pricing import PricingRecommendation, RiskLevel
from app.schemas.promotion import PromotionRecommendation
from app.schemas.listing import ListingRecommendation
from app.schemas.restock import RestockRecommendation
from app.services.orchestration.context import BusinessContext
from app.services.orchestration.conflicts import detect_relationships

PRIORITY_ORDER = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}
RISK_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def create_plan(context: BusinessContext, results: list[AgentResult]) -> ActionPlan:
    conflicts, relationships = detect_relationships(results)
    conflict_ids = {conflict.product_id for conflict in conflicts if conflict.type == "pricing_inventory_conflict"}
    promotion_conflicts = {c.product_id for c in conflicts if c.type != "pricing_inventory_conflict"}
    failed_restock = {r.product_id for r in results if r.agent_name == AgentName.RESTOCK and not r.success}
    recommendations = []
    for result in results:
        if not result.success:
            continue
        rec = result.recommendation
        if isinstance(rec, RestockRecommendation):
            action = "restock" if rec.recommended_quantity > 0 else "review_inventory" if rec.risk_level != RiskLevel.LOW else "monitor_inventory"
            priority = Priority.CRITICAL if rec.stockout_risk else Priority.HIGH if rec.risk_level == RiskLevel.HIGH else Priority.MEDIUM if rec.recommended_quantity else Priority.LOW
            reason = "Prioritize inventory review before pricing changes." if rec.risk_level == RiskLevel.HIGH else "Inventory urgency follows stockout exposure and replenishment need."
            recommendations.append(PlanRecommendation(agent=result.agent_name, product_id=result.product_id,
                priority=priority, action=action, recommended_quantity=rec.recommended_quantity, coordination_reason=reason))
        elif isinstance(rec, PricingRecommendation):
            discount = rec.recommended_price < rec.current_price
            deferred = discount and (rec.product_id in conflict_ids or rec.product_id in failed_restock)
            if deferred:
                reason = "Defer discount and hold current price until inventory replenishment risk is resolved or analysis succeeds."
            else:
                reason = "Review the bounded pricing proposal; monitor inventory sensitivity." if rec.recommended_price != rec.current_price else "Hold current price based on the agent's available evidence."
            recommendations.append(PlanRecommendation(agent=result.agent_name, product_id=result.product_id,
                priority=Priority.LOW if deferred or rec.recommended_price == rec.current_price else Priority.MEDIUM,
                action="hold_price" if deferred or rec.recommended_price == rec.current_price else "review_price_change",
                recommended_price=rec.current_price if deferred else rec.recommended_price,
                deferred=deferred, coordination_reason=reason))
        elif isinstance(rec, PromotionRecommendation):
            deferred = rec.promotion_recommended and (rec.product_id in promotion_conflicts or rec.product_id in failed_restock)
            recommendations.append(PlanRecommendation(agent=result.agent_name, product_id=result.product_id,
                priority=Priority.LOW, action="review_promotion" if rec.promotion_recommended and not deferred else "no_promotion",
                recommended_price=rec.current_price if deferred else rec.promotional_price,
                deferred=deferred, coordination_reason="Defer promotion until inventory or base-price conflicts are resolved." if deferred else rec.reason))
        elif isinstance(rec, ListingRecommendation):
            recommendations.append(PlanRecommendation(agent=result.agent_name, product_id=result.product_id,
                priority=Priority.LOW, action="review_listing", coordination_reason=rec.reason))
    recommendations.sort(key=lambda item: (PRIORITY_ORDER[item.priority], item.product_id, item.agent.value))
    complete = all(result.success for result in results)
    overall_risk = max((result.risk_level for result in results), key=lambda risk: RISK_ORDER[risk], default=RiskLevel.LOW)
    if not complete or conflicts:
        overall_risk = RiskLevel.HIGH
    confidence = min((result.confidence for result in results), default=0)
    if conflicts:
        confidence *= 0.8
    summary = f"Reviewed {len(context.products)} products; {len(recommendations)} advisory recommendations."
    if any(item.priority == Priority.CRITICAL for item in recommendations):
        summary += " Inventory replenishment or verification is the highest priority because stock may run out by supplier arrival."
    if conflicts:
        summary += f" {len(conflicts)} cross-agent conflicts: resolve inventory or pricing conflicts before discounts."
    if relationships:
        summary += " Compatible proposals are explained separately; monitor inventory health."
    if not complete:
        summary += " Plan incomplete: some agent analyses failed; successful recommendations are preserved."
    return ActionPlan(merchant_id=context.request.merchant_id, goal=context.request.goal,
        summary=summary, selected_agents=list(context.selected_agents),
        selection_reason=f"Goal '{context.request.goal.value}' maps to {', '.join(context.selected_agents)} by the supported-goal routing table.",
        recommendations=recommendations, agent_results=results, conflicts=conflicts,
        relationships=relationships, overall_risk=overall_risk,
        overall_confidence=round(confidence, 2), approval_required=True,
        complete=complete, created_at=context.as_of)
