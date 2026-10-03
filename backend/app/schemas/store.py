"""Read-only merchant dashboard contracts."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict
from app.schemas.product import ProductDetailResponse
from app.schemas.pricing import PricingRecommendation, RiskLevel
from app.schemas.listing import ListingRecommendation
from app.schemas.promotion import PromotionRecommendation
from app.schemas.restock import RestockRecommendation


class MerchantSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    store_name: str


class CatalogProduct(ProductDetailResponse):
    sales_velocity: float
    recent_units: int
    days_remaining: float | None
    stockout_risk: bool | None
    inventory_status: Literal["Healthy", "Low Stock", "Critical", "Out of Stock", "Missing", "Invalid"]


class CatalogSnapshot(BaseModel):
    products: list[CatalogProduct]
    total_products: int
    low_stock_products: int
    potential_stockouts: int
    available_units: int
    recent_orders: int
    revenue: Decimal
    lookback_days: int
    as_of: datetime
    has_more: bool


class SavedRecommendation(BaseModel):
    id: int
    product_id: int | None
    product_name: str | None
    agent: str
    title: str
    description: str | None
    confidence: float
    risk_level: RiskLevel | None
    status: str
    created_at: datetime
    payload: PricingRecommendation | RestockRecommendation | PromotionRecommendation | ListingRecommendation | None
