"""Pure decision engine; contains no database or external actions."""
from decimal import Decimal
from app.schemas.restock import RestockPolicy, RestockRecommendation
from app.services.restock.signals import RestockSignals
from app.services.restock.rules import ceil_units, cap_reorder_quantity, calculate_confidence, classify_risk


def calculate_restock_recommendation(
    signals: RestockSignals, policy: RestockPolicy | None = None,
) -> RestockRecommendation:
    policy = policy or RestockPolicy()
    available = signals.available_inventory
    velocity = Decimal(str(signals.sales_velocity))
    demand = velocity * Decimal(str(policy.lead_time_days))
    safety_stock = ceil_units(velocity * Decimal(str(policy.safety_stock_days)))
    days_remaining = round(float(Decimal(available) / velocity), 2) if velocity else None
    # Equality means stock is exhausted on arrival, so it is still an urgent risk.
    stockout_risk = velocity > 0 and Decimal(available) <= demand
    triggered = velocity > 0 and (
        available <= signals.reorder_point or Decimal(available) < demand + safety_stock
    )
    quantity = 0
    capped = False
    if signals.status != "active":
        reason = "Product is not active. No replenishment recommended; review product status."
    elif velocity == 0:
        reason = "No recent sales demand. No additional inventory recommended solely from reorder thresholds."
    elif not signals.has_sufficient_data:
        reason = "Insufficient sales history. No reorder recommended until demand is verified."
    elif triggered:
        # Existing reorder_quantity is an extra replenishment buffer, not a supplier minimum.
        target = demand + safety_stock + signals.reorder_quantity
        quantity, capped = cap_reorder_quantity(ceil_units(target - available), policy.max_reorder_quantity)
        reason = "Available inventory reached the reorder point or does not cover lead-time demand plus safety stock."
        if stockout_risk:
            reason += " Stock may be exhausted before or when replenishment arrives."
        if capped:
            reason += f" Recommended quantity capped at {policy.max_reorder_quantity}; review remaining stockout exposure."
    else:
        reason = "Current inventory sufficiently covers projected demand and reorder thresholds."
    return RestockRecommendation(
        product_id=signals.product_id, current_inventory=signals.quantity,
        available_inventory=available, sales_velocity=signals.sales_velocity,
        estimated_days_remaining=days_remaining, recommended_quantity=quantity,
        reason=reason, confidence=calculate_confidence(signals),
        risk_level=classify_risk(stockout_risk, triggered, capped),
        reorder_point=signals.reorder_point, lead_time_days=policy.lead_time_days,
        safety_stock=safety_stock, projected_demand_during_lead_time=float(demand),
        stockout_risk=stockout_risk,
    )
