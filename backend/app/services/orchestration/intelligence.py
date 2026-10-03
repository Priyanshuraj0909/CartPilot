"""Goal-aware relationships, safety overrides, dependencies and bounded action queue."""
from collections import defaultdict
from app.core.config import settings
from app.schemas.orchestration import (ActionPlan, AgentName, AgentResult, Goal, OpportunitySummary,
    PrioritizedAction, Priority, RecommendationRelationship, PlanRecommendation, Conflict, ProductOpportunity)
from app.schemas.pricing import PricingRecommendation, RiskLevel
from app.schemas.restock import RestockRecommendation
from app.schemas.promotion import PromotionRecommendation
from app.schemas.listing import ListingRecommendation
from app.services.orchestration.coordinator import RISK_ORDER, PRIORITY_ORDER
from app.services.orchestration.strategy import goal_score


def coordinate(base: ActionPlan, opportunities: list[ProductOpportunity], scope_has_more: bool) -> ActionPlan:
    goal = base.goal
    items: dict[str, PrioritizedAction] = {}
    relations = []
    results = {(r.product_id, r.agent_name): r for r in base.agent_results}
    opportunities_by_id = {o.product_id: o for o in opportunities}
    grouped = defaultdict(dict)

    def relation(pid, a, b, kind, text, resolution, severity='low'):
        relations.append(RecommendationRelationship(product_id=pid, agent_a=a, agent_b=b,
            relationship_type=kind, severity=severity, explanation=text, recommended_resolution=resolution))

    def block(item, reason, dependency=None):
        updates = {'blocked': True, 'blocked_reason': reason, 'approval_candidate': False}
        if dependency:
            updates['depends_on'] = sorted(set([*item.depends_on, dependency]))
        items[item.id] = item.model_copy(update=updates)

    for result in base.agent_results:
        if not result.success:
            continue
        rec = result.recommendation
        opportunity = opportunities_by_id[result.product_id]
        grouped[result.product_id][result.agent_name] = rec
        kind, strength, critical, candidate = None, 1., False, True
        if isinstance(rec, RestockRecommendation):
            if rec.recommended_quantity > 0:
                kind = 'restock'
            elif opportunity.stockout_risk:
                kind, candidate = 'review_inventory', False
            critical = opportunity.stockout_risk
            strength = 1. if critical else .6
        elif isinstance(rec, PricingRecommendation):
            if rec.recommended_price != rec.current_price:
                kind = 'price_change'
                strength = min(1., abs(rec.price_change_percent) / 5)
        elif isinstance(rec, PromotionRecommendation):
            if rec.promotion_recommended:
                kind = 'promotion'
        elif isinstance(rec, ListingRecommendation):
            if rec.current_title != rec.recommended_title or rec.current_description != rec.recommended_description or rec.quality_score < settings.LISTING_POOR_QUALITY_THRESHOLD:
                kind = 'listing_update'
                strength = 1. if rec.quality_score < settings.LISTING_POOR_QUALITY_THRESHOLD else .5
                candidate = rec.current_title != rec.recommended_title or rec.current_description != rec.recommended_description
        if kind is None:
            continue
        score = goal_score(goal, result.agent_name, strength, rec.confidence)
        priority = Priority.CRITICAL if critical else Priority.HIGH if score >= .15 or (kind == 'listing_update' and strength == 1) else Priority.MEDIUM if score >= .05 else Priority.LOW
        if kind == 'price_change' and goal == Goal.BALANCED:
            priority = Priority.MEDIUM
        aid = f'{result.product_id}:{result.agent_name.value}'
        items[aid] = PrioritizedAction(id=aid, rank=1, product_id=result.product_id,
            product_name=opportunity.product_name, agent=result.agent_name, action_type=kind,
            priority=priority, priority_score=score, reason=f'{rec.reason} Goal strategy: {goal.value}; score = goal weight × signal strength × confidence ({score:.4f}).',
            confidence=rec.confidence, risk=rec.risk_level, approval_candidate=candidate)

    for opportunity in opportunities:
        pid = opportunity.product_id
        pair = grouped[pid]
        price = pair.get(AgentName.PRICING)
        promotion = pair.get(AgentName.PROMOTION)
        listing = pair.get(AgentName.LISTING)
        restock_id, price_id, promo_id, listing_id = [f'{pid}:{name}' for name in ('restock','pricing','promotion','listing')]
        stock_failed = (pid, AgentName.RESTOCK) in results and not results[(pid, AgentName.RESTOCK)].success
        unsafe = opportunity.stockout_risk or not opportunity.inventory_known or stock_failed
        if unsafe:
            if restock_id not in items:
                items[restock_id] = PrioritizedAction(id=restock_id, rank=1, product_id=pid, product_name=opportunity.product_name,
                    agent=AgentName.RESTOCK, action_type='review_inventory', priority=Priority.CRITICAL, priority_score=0,
                    reason='Inventory assessment failed or supply is unverified; verify stock before operational changes.',
                    confidence=0, risk=RiskLevel.HIGH, approval_candidate=False)
            reason = 'Inventory is constrained or unverified; resolve replenishment and reanalyze before stimulating demand.'
            # Preserve a visible safety decision even if the specialist correctly returns no promotion.
            if promo_id not in items:
                items[promo_id] = PrioritizedAction(id=promo_id, rank=1, product_id=pid, product_name=opportunity.product_name,
                    agent=AgentName.PROMOTION, action_type='promotion', priority=Priority.LOW, priority_score=0,
                    reason='Demand stimulation is suppressed by the inventory safety override.', confidence=0, risk=RiskLevel.HIGH,
                    blocked=True, blocked_reason=reason, depends_on=[restock_id], approval_candidate=False)
            else:
                block(items[promo_id], reason, restock_id)
            relation(pid, AgentName.PROMOTION, AgentName.RESTOCK, 'conflict', reason, 'Restock or verify physical inventory first.', 'high')
            relation(pid, AgentName.PROMOTION, AgentName.RESTOCK, 'dependency', 'Promotion requires healthy verified inventory.', 'Reanalyze after actual replenishment; a simulated restock does not satisfy this dependency.', 'high')
            if isinstance(price, PricingRecommendation) and price.recommended_price < price.current_price and price_id in items:
                block(items[price_id], reason, restock_id)
                relation(pid, AgentName.PRICING, AgentName.RESTOCK, 'conflict', 'A price reduction could increase demand on constrained inventory.', 'Defer the reduction; replenish and reanalyze.', 'high')
                relation(pid, AgentName.PRICING, AgentName.RESTOCK, 'dependency', 'Price reduction requires current inventory health.', 'Verify replenishment before reviewing a reduction.', 'high')
            elif isinstance(price, PricingRecommendation) and price.recommended_price > price.current_price:
                relation(pid, AgentName.PRICING, AgentName.RESTOCK, 'synergy', 'A bounded increase can coexist with replenishment planning.', 'Prioritize replenishment and monitor demand.', 'medium')
        if price_id in items and promo_id in items and isinstance(promotion, PromotionRecommendation) and promotion.promotion_recommended:
            winner = AgentName.PROMOTION if goal in (Goal.EXCESS_REDUCTION, Goal.PERFORMANCE) or (goal == Goal.BALANCED and opportunity.excess_inventory and isinstance(price, PricingRecommendation) and price.recommended_price < price.current_price) else AgentName.PRICING
            loser_id = price_id if winner == AgentName.PROMOTION else promo_id
            if not items[promo_id].blocked:
                block(items[loser_id], f'Overlapping base-price and promotion changes: {winner.value} takes precedence for {goal.value}.')
            relation(pid, AgentName.PRICING, AgentName.PROMOTION, 'conflict', 'Base-price changes and temporary discounts must not overlap or stack.', f'Review {winner.value} first; defer the alternative and reanalyze.', 'medium')
        poor_listing = isinstance(listing, ListingRecommendation) and listing.quality_score < settings.LISTING_POOR_QUALITY_THRESHOLD
        if poor_listing and listing_id in items:
            if isinstance(promotion, PromotionRecommendation) and promotion.promotion_recommended:
                if promo_id in items and not items[promo_id].blocked:
                    block(items[promo_id], 'Review the poor listing and reassess demand before promotion.', listing_id)
                relation(pid, AgentName.PROMOTION, AgentName.LISTING, 'dependency', 'Listing quality should be reviewed before relying on discounts.', 'Review verified listing information, then reanalyze promotion.')
                relation(pid, AgentName.LISTING, AgentName.PROMOTION, 'synergy', 'Poor listing information may contribute to weak demand; listing improvements support promotion review.', 'Review factual listing content before or alongside a controlled promotion.')
            if isinstance(price, PricingRecommendation) and price.recommended_price < price.current_price and price_id in items:
                block(items[price_id], 'Review listing quality and reassess demand before assuming price is the problem.', listing_id)
                relation(pid, AgentName.PRICING, AgentName.LISTING, 'dependency', 'Poor listing quality makes price reduction a secondary remedy.', 'Improve or verify factual content, then reanalyze pricing.', 'medium')
        if AgentName.RESTOCK in pair and AgentName.LISTING in pair:
            relation(pid, AgentName.RESTOCK, AgentName.LISTING, 'independent', 'Factual listing review and replenishment address separate issues.', 'Review independently; inventory safety remains first.')

    for item in list(items.values()):
        if not opportunities_by_id[item.product_id].active and item.approval_candidate:
            block(item, 'Product is inactive; operational changes require an active product and fresh review.')

    ordered = sorted(items.values(), key=lambda i: (PRIORITY_ORDER[i.priority], -i.priority_score, i.product_id, i.agent.value))
    ordered = [item.model_copy(update={'rank': index + 1}) for index, item in enumerate(ordered)]
    available = [item for item in ordered if not item.blocked]
    selected, omitted = available[:settings.MAX_ACTIONS_PER_PLAN], available[settings.MAX_ACTIONS_PER_PLAN:]
    blocked = [item for item in ordered if item.blocked]
    # Ranks in the primary queue are contiguous; other queues retain their full-plan ranks.
    selected = [item.model_copy(update={'rank': index + 1}) for index, item in enumerate(selected)]
    warnings = []
    if omitted:
        critical = sum(i.priority == Priority.CRITICAL for i in omitted)
        warnings.append(f'Action budget: {len(omitted)} additional actions remain visible outside the priority queue, including {critical} critical items.')
    if scope_has_more:
        warnings.append('Store analysis was bounded by the product limit; more active products require another scoped analysis.')
    failures = sum(not r.success for r in base.agent_results)
    confidence = min((r.confidence for r in base.agent_results), default=0)
    if any(r.relationship_type == 'conflict' for r in relations):
        confidence *= .8
    if scope_has_more:
        confidence *= .8
    overall_risk = max([r.risk_level for r in base.agent_results] + [i.risk for i in ordered], key=lambda r: RISK_ORDER[r], default=RiskLevel.LOW)
    if failures or scope_has_more or any(o.stockout_risk for o in opportunities):
        overall_risk = RiskLevel.HIGH
    summary_counts = OpportunitySummary(pricing_opportunities=[o.product_id for o in opportunities if o.pricing_opportunity],
        restock_risks=[o.product_id for o in opportunities if o.stockout_risk],
        promotion_opportunities=[o.product_id for o in opportunities if o.excess_inventory and not o.stockout_risk],
        listing_issues=[o.product_id for o in opportunities if o.listing_issue])
    summary = (f'{len(opportunities)} products analyzed for {goal.value}: {len(summary_counts.restock_risks)} inventory risks, '
        f'{len(summary_counts.promotion_opportunities)} excess/slow movers, {len(summary_counts.pricing_opportunities)} pricing opportunities, '
        f'{len(summary_counts.listing_issues)} listing issues. Review {len(selected)} priority actions; {len(blocked)} proposals are blocked.')
    if failures:
        summary += f' Incomplete: {failures} specialist analyses failed; successful results remain available.'
    if selected:
        summary += f' First: {selected[0].agent.value} for {selected[0].product_name} ({selected[0].priority.value}).'
    recommendations = []
    for item in [*selected, *blocked]:
        result = results.get((item.product_id, item.agent))
        rec = result.recommendation if result and result.success else None
        action = {'price_change':'review_price_change', 'promotion':'review_promotion', 'listing_update':'review_listing', 'restock':'restock', 'review_inventory':'review_inventory'}[item.action_type]
        recommendations.append(PlanRecommendation(agent=item.agent, product_id=item.product_id, priority=item.priority,
            action=action, deferred=item.blocked, coordination_reason=item.blocked_reason or item.reason,
            recommended_price=rec.recommended_price if isinstance(rec, PricingRecommendation) else rec.promotional_price if isinstance(rec, PromotionRecommendation) else None,
            recommended_quantity=rec.recommended_quantity if isinstance(rec, RestockRecommendation) else None))
    conflicts = [Conflict(type='pricing_inventory_conflict' if r.agent_a == AgentName.PRICING and r.agent_b == AgentName.RESTOCK else 'pricing_promotion_conflict' if r.agent_b == AgentName.PROMOTION else 'promotion_inventory_conflict',
        product_id=r.product_id, severity=r.severity, message=r.explanation, resolution=r.recommended_resolution) for r in relations if r.relationship_type=='conflict']
    return base.model_copy(update={'products_analyzed': len(opportunities), 'opportunities': opportunities,
        'opportunity_summary': summary_counts, 'recommendation_relationships': relations,
        'prioritized_actions': selected, 'blocked_actions': blocked, 'omitted_actions': omitted,
        'recommendations': recommendations, 'conflicts': conflicts, 'relationships': [], 'summary': summary,
        'overall_risk': overall_risk, 'overall_confidence': round(confidence,2), 'complete': not failures and not scope_has_more,
        'scope_has_more': scope_has_more, 'warnings': warnings,
        'selection_reason': 'Specialists are selected per product from fresh opportunities and goal strategy; inventory safety overrides optimization.'})
