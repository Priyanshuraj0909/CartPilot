"""External identities and sync summaries; merchant data lives in existing tables."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class ShopifyConnection(Base, TimestampMixin):
    __tablename__ = 'shopify_connections'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id',ondelete='CASCADE'), unique=True, nullable=False)
    store_domain: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    sync_in_progress: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false', nullable=False)
    last_sync: Mapped[dict | None] = mapped_column(JSON)

class ExternalProductMapping(Base):
    __tablename__ = 'external_product_mappings'
    __table_args__ = (UniqueConstraint('connection_id','external_variant_id',name='uq_shopify_variant'),)
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey('shopify_connections.id',ondelete='CASCADE'),nullable=False,index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id',ondelete='CASCADE'),unique=True,nullable=False)
    external_product_id: Mapped[str] = mapped_column(String(100),nullable=False)
    external_variant_id: Mapped[str] = mapped_column(String(100),nullable=False)
    inventory_item_id: Mapped[str] = mapped_column(String(100),nullable=False)
    external_sku: Mapped[str | None] = mapped_column(String(255))
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    inventory_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inventory_snapshot: Mapped[dict | None] = mapped_column(JSON)

class ExternalOrderMapping(Base):
    __tablename__ = 'external_order_mappings'
    __table_args__ = (UniqueConstraint('connection_id','external_order_id',name='uq_shopify_order'),)
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey('shopify_connections.id',ondelete='CASCADE'),nullable=False,index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id',ondelete='CASCADE'),unique=True,nullable=False)
    external_order_id: Mapped[str] = mapped_column(String(100),nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
