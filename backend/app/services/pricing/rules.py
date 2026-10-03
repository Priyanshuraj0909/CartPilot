"""Deterministic pricing rules, safety guardrails, confidence, and risk scoring."""

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from math import isfinite
from typing import Tuple

from app.schemas.pricing import RiskLevel
from app.services.pricing.signals import ProductPricingSignals


def apply_below_cost_guardrail(
    proposed_price: Decimal,
    cost_price: Decimal,
    min_margin_percent: float = 0.0,
) -> Tuple[Decimal, bool]:
    """Ensure recommended price never drops below cost price (Rule 1).

    Returns:
        (enforced_price, was_clamped_flag)
    """
    if not isfinite(min_margin_percent) or min_margin_percent < 0:
        raise ValueError("Minimum margin must be finite and nonnegative.")
    margin_multiplier = Decimal("1.0") + (Decimal(str(min_margin_percent)) / Decimal("100.0"))
    minimum_floor = (cost_price * margin_multiplier).quantize(Decimal("0.01"), rounding=ROUND_CEILING)

    if proposed_price < minimum_floor:
        return minimum_floor, True
    return proposed_price, False


def apply_price_change_caps(
    current_price: Decimal,
    proposed_price: Decimal,
    max_increase_percent: float,
    max_decrease_percent: float,
) -> Tuple[Decimal, bool, bool]:
    """Enforce maximum increase (Rule 2) and maximum decrease (Rule 3) boundaries.

    Returns:
        (capped_price, was_increase_capped, was_decrease_capped)
    """
    if not current_price.is_finite() or current_price <= 0 or not proposed_price.is_finite():
        raise ValueError("Prices must be finite and current price positive.")
    if not isfinite(max_increase_percent) or max_increase_percent < 0:
        raise ValueError("Maximum increase must be finite and nonnegative.")
    if not isfinite(max_decrease_percent) or not 0 <= max_decrease_percent < 100:
        raise ValueError("Maximum decrease must be finite and between 0 and 100 exclusive.")
    increase_limit = Decimal("1.0") + (Decimal(str(max_increase_percent)) / Decimal("100.0"))
    ceiling_price = (current_price * increase_limit).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)

    decrease_limit = Decimal("1.0") - (Decimal(str(max_decrease_percent)) / Decimal("100.0"))
    floor_price = (current_price * decrease_limit).quantize(Decimal("0.01"), rounding=ROUND_CEILING)

    was_increase_capped = False
    was_decrease_capped = False
    final_price = proposed_price

    if proposed_price > ceiling_price:
        final_price = ceiling_price
        was_increase_capped = True
    elif proposed_price < floor_price:
        final_price = floor_price
        was_decrease_capped = True

    return final_price, was_increase_capped, was_decrease_capped


def calculate_confidence(signals: ProductPricingSignals) -> float:
    """Calculate deterministic confidence score [0.0 - 1.0] from data availability."""
    if not signals.has_sufficient_data:
        return 0.20

    confidence = 0.35

    # Lookback order volume stability
    if signals.orders_count_lookback >= 15:
        confidence += 0.25
    elif signals.orders_count_lookback >= 5:
        confidence += 0.15

    # Inventory signal visibility
    if signals.total_quantity > 0:
        confidence += 0.15

    # Price history record availability
    if signals.historical_price_changes_count > 0:
        confidence += 0.10

    # Sales velocity consistency
    if signals.sales_velocity >= 0.5:
        confidence += 0.15

    return min(1.0, max(0.10, round(confidence, 2)))


def calculate_risk_level(
    signals: ProductPricingSignals,
    final_price: Decimal,
    is_cost_capped: bool,
    is_increase_capped: bool,
    is_decrease_capped: bool,
) -> RiskLevel:
    """Classify risk level (low, medium, high) based on data, margin, and stock constraints."""
    # 1. High risk criteria
    if not signals.has_sufficient_data:
        return RiskLevel.HIGH

    if is_cost_capped:
        return RiskLevel.HIGH

    if signals.is_low_stock:
        return RiskLevel.HIGH

    # Margin check: margin < 5% is high risk
    if final_price > Decimal("0.00"):
        margin = (final_price - signals.cost_price) / final_price
        if margin < Decimal("0.05"):
            return RiskLevel.HIGH

    # 2. Medium risk criteria
    if is_increase_capped or is_decrease_capped:
        return RiskLevel.MEDIUM

    price_delta_pct = abs(float((final_price - signals.current_price) / signals.current_price) * 100.0)
    if price_delta_pct >= 5.0:
        return RiskLevel.MEDIUM

    # 3. Low risk criteria: healthy inventory, high confidence, small change
    return RiskLevel.LOW
