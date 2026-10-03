"""Small deterministic replenishment rules."""
from decimal import Decimal, ROUND_CEILING
from app.schemas.pricing import RiskLevel
from app.services.restock.signals import RestockSignals


def ceil_units(value: Decimal) -> int:
    """Round required stock upward to whole units, never below zero."""
    return max(0, int(value.to_integral_value(rounding=ROUND_CEILING)))


def cap_reorder_quantity(quantity: int, maximum: int) -> tuple[int, bool]:
    if maximum <= 0:
        raise ValueError("Maximum reorder quantity must be positive.")
    safe_quantity = max(0, quantity)
    return min(safe_quantity, maximum), safe_quantity > maximum


def calculate_confidence(signals: RestockSignals) -> float:
    """Availability/volume heuristic, not a calibrated stockout probability."""
    if not signals.has_sufficient_data or signals.sales_velocity == 0 or signals.status != "active":
        return 0.20
    # Known inventory contributes .15; observations contribute at most .30.
    observation_score = 0.30 if signals.recent_orders >= 15 else 0.20 if signals.recent_orders >= 5 else 0.10
    return round(0.40 + 0.15 + observation_score, 2)


def classify_risk(stockout_risk: bool, triggered: bool, capped: bool) -> RiskLevel:
    if stockout_risk or capped:
        return RiskLevel.HIGH
    return RiskLevel.MEDIUM if triggered else RiskLevel.LOW
