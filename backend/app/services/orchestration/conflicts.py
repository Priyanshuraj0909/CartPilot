"""Cross-agent interactions preserve original proposals and explain coordination."""
from app.schemas.orchestration import AgentName, AgentResult, Conflict, Relationship
from app.schemas.pricing import PricingRecommendation, RiskLevel
from app.schemas.restock import RestockRecommendation
from app.schemas.listing import ListingRecommendation
from app.core.config import settings
from app.schemas.promotion import PromotionRecommendation


def detect_relationships(results: list[AgentResult]) -> tuple[list[Conflict], list[Relationship]]:
    pairs: dict[int, dict[AgentName, AgentResult]] = {}
    for result in results:
        if result.success:
            pairs.setdefault(result.product_id, {})[result.agent_name] = result
    conflicts, relationships = [], []
    for product_id, pair in sorted(pairs.items()):
        pricing = pair[AgentName.PRICING].recommendation if AgentName.PRICING in pair else None
        restock = pair[AgentName.RESTOCK].recommendation if AgentName.RESTOCK in pair else None
        promotion = pair[AgentName.PROMOTION].recommendation if AgentName.PROMOTION in pair else None
        listing = pair[AgentName.LISTING].recommendation if AgentName.LISTING in pair else None
        if isinstance(listing, ListingRecommendation) and listing.quality_score < settings.LISTING_POOR_QUALITY_THRESHOLD:
            if isinstance(promotion, PromotionRecommendation) and promotion.promotion_recommended:
                relationships.append(Relationship(product_id=product_id,
                    message="Improve the incomplete listing before or alongside a controlled promotion; reassess demand before relying on discounts."))
            if isinstance(pricing, PricingRecommendation) and pricing.recommended_price < pricing.current_price:
                relationships.append(Relationship(product_id=product_id,
                    message="Review listing completeness before relying on a price reduction; incomplete information may contribute to weak demand."))
        if isinstance(pricing, PricingRecommendation) and isinstance(restock, RestockRecommendation) and restock.risk_level == RiskLevel.HIGH:
            if pricing.recommended_price < pricing.current_price:
                conflicts.append(Conflict(product_id=product_id,
                    message="Price reduction may increase demand while inventory has high replenishment risk.",
                    resolution="Restock or verify inventory first; defer the price reduction until inventory health improves."))
            elif pricing.recommended_price > pricing.current_price:
                relationships.append(Relationship(product_id=product_id,
                    message="A moderate price increase is compatible with constrained inventory; prioritize replenishment and monitor demand."))
        if isinstance(promotion, PromotionRecommendation) and promotion.promotion_recommended:
            if isinstance(restock, RestockRecommendation) and restock.risk_level == RiskLevel.HIGH:
                conflicts.append(Conflict(type="promotion_inventory_conflict", product_id=product_id,
                    message="Demand-stimulating promotion conflicts with current stockout risk.",
                    resolution="Replenish or verify inventory before stimulating additional demand; defer promotion."))
            if isinstance(pricing, PricingRecommendation):
                if pricing.recommended_price != pricing.current_price:
                    conflicts.append(Conflict(type="pricing_promotion_conflict", product_id=product_id,
                        message="A base-price change and a temporary promotion propose different prices for the same product.",
                        resolution="Review the pricing proposal first; defer promotion to avoid overlapping price changes or stacked discounts."))
                else:
                    relationships.append(Relationship(product_id=product_id,
                        message="Holding the base price is compatible with separately reviewing a controlled temporary promotion for excess inventory."))
    return conflicts, relationships
