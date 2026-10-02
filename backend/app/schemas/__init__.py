"""Pydantic schemas package for request/response serialization."""

from app.schemas.health import HealthResponse, DetailedHealthResponse
from app.schemas.merchant import MerchantBase, MerchantCreate, MerchantUpdate, MerchantResponse
from app.schemas.product import ProductBase, ProductCreate, ProductUpdate, ProductResponse, ProductDetailResponse
from app.schemas.inventory import InventoryBase, InventoryUpdate, InventoryResponse
from app.schemas.order import (
    OrderItemBase,
    OrderItemCreate,
    OrderItemResponse,
    OrderBase,
    OrderCreate,
    OrderResponse,
    OrderDetailResponse,
)
from app.schemas.price_history import PriceHistoryResponse
from app.schemas.recommendation import (
    RecommendationBase,
    RecommendationCreate,
    RecommendationResponse,
)
from app.schemas.agent_run import AgentRunBase, AgentRunResponse
from app.schemas.audit_log import AuditLogResponse

__all__ = [
    "HealthResponse",
    "DetailedHealthResponse",
    "MerchantBase",
    "MerchantCreate",
    "MerchantUpdate",
    "MerchantResponse",
    "ProductBase",
    "ProductCreate",
    "ProductUpdate",
    "ProductResponse",
    "ProductDetailResponse",
    "InventoryBase",
    "InventoryUpdate",
    "InventoryResponse",
    "OrderItemBase",
    "OrderItemCreate",
    "OrderItemResponse",
    "OrderBase",
    "OrderCreate",
    "OrderResponse",
    "OrderDetailResponse",
    "PriceHistoryResponse",
    "RecommendationBase",
    "RecommendationCreate",
    "RecommendationResponse",
    "AgentRunBase",
    "AgentRunResponse",
    "AuditLogResponse",
]
