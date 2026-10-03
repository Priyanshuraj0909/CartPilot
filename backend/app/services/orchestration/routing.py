"""Deterministic, explicit goal-to-agent selection."""
from app.schemas.orchestration import AgentName, Goal

GOAL_AGENTS: dict[Goal, tuple[AgentName, ...]] = {
    Goal.IMPROVE_LISTINGS: (AgentName.LISTING,),
    Goal.CATALOG_QUALITY: (AgentName.LISTING,),
    Goal.DISCOVERABILITY: (AgentName.LISTING,),
    Goal.PRODUCT_INFORMATION: (AgentName.LISTING,),
    Goal.PRODUCT_PERFORMANCE: (AgentName.PRICING, AgentName.PROMOTION, AgentName.LISTING),
    Goal.LISTING_AND_INVENTORY: (AgentName.RESTOCK, AgentName.LISTING),
    Goal.MOVE_SLOW_INVENTORY: (AgentName.PROMOTION,),
    Goal.INCREASE_SELL_THROUGH: (AgentName.PROMOTION,),
    Goal.REDUCE_EXCESS_INVENTORY: (AgentName.PROMOTION,),
    Goal.SLOW_REVENUE: (AgentName.PROMOTION,),
    Goal.ALL_HEALTH: (AgentName.PRICING, AgentName.RESTOCK, AgentName.PROMOTION),
    Goal.OPTIMIZE_PRICING: (AgentName.PRICING,),
    Goal.INCREASE_REVENUE: (AgentName.PRICING,),
    Goal.AVOID_STOCKOUTS: (AgentName.RESTOCK,),
    Goal.PROTECT_INVENTORY: (AgentName.RESTOCK,),
    Goal.REVENUE_AND_STOCKOUTS: (AgentName.PRICING, AgentName.RESTOCK),
    Goal.REVENUE_AND_HEALTH: (AgentName.PRICING, AgentName.RESTOCK),
}


def select_agents(goal: Goal) -> tuple[AgentName, ...]:
    return GOAL_AGENTS[goal]
