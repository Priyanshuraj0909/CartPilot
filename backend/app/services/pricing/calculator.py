"""Core decision engine evaluating pricing rules, constraints, and generating recommendations."""

from decimal import Decimal
from app.core.config import settings
from app.schemas.pricing import PricingRecommendation
from app.services.pricing.rules import (
    apply_below_cost_guardrail,
    apply_price_change_caps,
    calculate_confidence,
    calculate_risk_level,
)
from app.services.pricing.signals import ProductPricingSignals


def calculate_pricing_recommendation(
    signals: ProductPricingSignals,
    max_increase_percent: float = settings.MAX_PRICE_INCREASE_PERCENT,
    max_decrease_percent: float = settings.MAX_PRICE_DECREASE_PERCENT,
    min_margin_percent: float = settings.MIN_MARGIN_PERCENT,
) -> PricingRecommendation:
    """Evaluate signals against deterministic pricing rules and return a validated recommendation."""
    if signals.cost_price is None:
        raise ValueError("Cost price is unknown; margin-dependent pricing is unavailable.")
    if not signals.current_price.is_finite() or not signals.cost_price.is_finite():
        raise ValueError("Prices must be finite.")
    if signals.current_price <= Decimal("0.00"):
        raise ValueError(f"Invalid current price ({signals.current_price}): price must be strictly positive.")
    if signals.cost_price < Decimal("0.00"):
        raise ValueError(f"Invalid cost price ({signals.cost_price}): cost price cannot be negative.")

    adjustment = Decimal(str(settings.PRICING_ADJUSTMENT_PERCENT)) / Decimal("100")
    # 1. Rule Evaluation
    if not signals.has_inventory:
        proposed_price = signals.current_price
        reason = "Inventory data is unavailable. Maintaining current price pending inventory verification."
    elif not signals.has_sufficient_data:
        # Rule 7: Insufficient historical sales data
        proposed_price = signals.current_price
        reason = (
            "Insufficient historical sales data for a reliable pricing adjustment. "
            "Maintaining current price to avoid uncalibrated merchant risk."
        )
    elif signals.is_low_stock:
        # Rule 6: Low inventory scenarios
        if signals.is_strong_sales:
            # Low stock + strong demand -> moderate increase to preserve inventory and capture margin
            proposed_price = round(signals.current_price * (Decimal("1") + adjustment), 2)
            reason = (
                "Critically low inventory paired with strong sales velocity. "
                "Recommending a moderate price increase to capture margin and reduce stockout risk."
            )
        else:
            # Low stock + weak/moderate demand -> preserve price, never discount low stock
            proposed_price = signals.current_price
            reason = (
                "Low inventory detected. Preserving current price without discounting "
                "to avoid exacerbating stock depletion."
            )
    elif signals.is_healthy_inventory and signals.is_strong_sales:
        # Rule 4: Healthy inventory + strong sales
        proposed_price = round(signals.current_price * (Decimal("1") + adjustment), 2)
        reason = (
            "Strong sales velocity supported by healthy inventory levels indicates strong demand. Recommending a controlled price increase."
        )
    elif signals.is_high_inventory and signals.is_weak_sales:
        # Rule 5: Low sales / slow movement + high inventory
        proposed_price = round(signals.current_price * (Decimal("1") - adjustment), 2)
        reason = (
            "High inventory levels combined with slow sales velocity. "
            "Recommending a promotional price reduction to stimulate turnover."
        )
    else:
        # Balanced market conditions
        proposed_price = signals.current_price
        reason = (
            "Sales velocity and inventory levels are balanced at current price point. "
            "No price adjustment recommended."
        )

    # 2. Guardrail Enforcement
    # Cap maximum increase / decrease
    capped_price, was_inc_capped, was_dec_capped = apply_price_change_caps(
        current_price=signals.current_price,
        proposed_price=proposed_price,
        max_increase_percent=max_increase_percent,
        max_decrease_percent=max_decrease_percent,
    )

    # Enforce below-cost protection as a hard floor
    final_price, was_cost_capped = apply_below_cost_guardrail(
        proposed_price=capped_price,
        cost_price=signals.cost_price,
        min_margin_percent=min_margin_percent,
    )

    ceiling, _, _ = apply_price_change_caps(
        signals.current_price, final_price, max_increase_percent, max_decrease_percent
    )
    if ceiling != final_price:
        raise ValueError("Cost/margin floor conflicts with configured price change limits.")

    # Append guardrail notices to explanation
    if was_inc_capped:
        reason += f" (Capped at configured maximum price increase of {max_increase_percent}%)."
    elif was_dec_capped:
        reason += f" (Capped at configured maximum price decrease of {max_decrease_percent}%)."

    if was_cost_capped:
        reason += " (Clamped to prevent selling below unit cost price)."

    # 3. Derived Metrics & Scoring
    price_change_pct = round(
        float((final_price - signals.current_price) / signals.current_price) * 100.0,
        2,
    )
    confidence = calculate_confidence(signals)
    risk_level = calculate_risk_level(
        signals=signals,
        final_price=final_price,
        is_cost_capped=was_cost_capped,
        is_increase_capped=was_inc_capped,
        is_decrease_capped=was_dec_capped,
    )

    return PricingRecommendation(
        product_id=signals.product_id,
        current_price=signals.current_price,
        recommended_price=final_price,
        reason=reason,
        confidence=confidence,
        risk_level=risk_level,
        price_change_percent=price_change_pct,
        sales_velocity=signals.sales_velocity,
        inventory_quantity=signals.available_quantity,
        cost_price=signals.cost_price,
    )
