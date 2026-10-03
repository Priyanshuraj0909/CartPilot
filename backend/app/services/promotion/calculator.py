"""Pure candidate detection and Decimal guardrails; no actions or writes."""
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from app.schemas.promotion import PromotionPolicy, PromotionRecommendation
from app.services.promotion.signals import PromotionSignals, sales_trend


def calculate_promotion_recommendation(signals: PromotionSignals, policy: PromotionPolicy) -> PromotionRecommendation:
    p = signals.product
    price, cost = p.current_price, p.cost_price
    if cost is None:
        raise ValueError("Cost price is unknown; margin-dependent promotions are unavailable.")
    if not price.is_finite() or not cost.is_finite() or price <= 0 or cost < 0:
        raise ValueError("Promotion requires positive finite price and nonnegative finite cost.")
    trend = sales_trend(signals, policy)
    available = signals.restock.available_inventory
    days = available / p.sales_velocity if p.sales_velocity > 0 else None
    high = days > policy.high_inventory_days if days is not None else available >= policy.zero_sales_inventory
    weak = p.sales_velocity < policy.slow_sales_threshold or trend == "declining"
    discount = Decimal(0)
    risk = "low"
    confidence = .2 if signals.history_days < policy.lookback_days else .4
    confidence += .2 if p.total_historical_orders >= 3 else .1 if p.total_historical_orders else 0
    confidence += .15 if trend == "declining" else 0
    confidence = round(min(.9, confidence), 2)
    if p.status != "active":
        reason = "Product is inactive; no promotion recommended."
    elif available <= p.reorder_point or signals.restock.risk_level == "high" or signals.restock.stockout_risk:
        reason = "Promotion could worsen existing stockout risk or low available inventory; replenish or verify inventory first."
        risk = "high"
    elif signals.history_days < policy.lookback_days:
        reason = "Insufficient observation history; collect a complete sales window before recommending a promotion."
        risk = "high"
    elif not high:
        reason = "Inventory is not excessive relative to demand; no promotion recommended."
    elif not weak:
        reason = "Product already has healthy demand; no discount needed."
    else:
        desired = policy.severe_discount if p.sales_velocity == 0 else policy.moderate_discount if trend == "declining" else policy.mild_discount
        # Gross margin floor: price >= cost / (1 - margin). Never round the discount upward.
        floor = cost / (1 - policy.min_margin_percent / 100)
        safe_discount = max(Decimal(0), (1 - floor / price) * 100)
        discount = min(desired, policy.max_discount_percent, safe_discount).quantize(Decimal(".01"), rounding=ROUND_DOWN)
        candidate = (price * (1 - discount / 100)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        # Cent rounding can cross the margin floor for tiny prices. Decline conservatively.
        if discount <= 0 or candidate >= price or candidate < floor:
            discount = Decimal(0)
            reason = "Discount cannot safely preserve the configured retained gross margin; no promotion recommended."
            risk = "high"
        else:
            reason = "High available inventory combined with weak or declining sales suggests a controlled discount to improve sell-through."
            if discount < desired:
                reason += " Discount reduced by maximum-discount or retained-margin guardrails."
            risk = "high" if discount < min(desired, policy.max_discount_percent) else "medium" if discount >= 10 or p.total_historical_orders < 3 else "low"
    promotional = (price * (1 - discount / 100)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) if discount else price
    return PromotionRecommendation(product_id=p.product_id, current_price=price, cost_price=cost,
        promotion_recommended=discount > 0, promotion_type="discount" if discount else "none",
        discount_percentage=discount, promotional_price=promotional, reason=reason, confidence=confidence,
        risk_level=risk, available_inventory=available, sales_velocity=p.sales_velocity, sales_trend=trend,
        gross_margin_percent=float((price-cost)/price*100), retained_margin_percent=float((promotional-cost)/promotional*100),
        days_of_inventory=days, recent_units=signals.recent_units, previous_units=signals.previous_units,
        expected_effect="May improve sell-through of excess inventory while preserving margin; revenue lift is not guaranteed." if discount else "Preserve current price; review the evidence before stimulating demand.")
