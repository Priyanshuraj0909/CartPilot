"""Durable conversations, idempotent operations, merchant rules and handoff capabilities."""
from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ShoppingConversation(Base):
    __tablename__ = "shopping_conversations"
    shopper_hash: Mapped[str] = mapped_column(ForeignKey("shopper_sessions.token_hash", ondelete="CASCADE"), primary_key=True)
    messages: Mapped[list[dict]] = mapped_column(JSON, default=list)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[int] = mapped_column(BigInteger)


class CommerceOperation(Base):
    __tablename__ = "commerce_operations"
    __table_args__ = (UniqueConstraint("cart_id", "request_key", name="uq_commerce_operation_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("shopping_carts.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24))
    amount_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    provider_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[int] = mapped_column(BigInteger)


class CommerceRules(Base):
    __tablename__ = "commerce_rules"
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), primary_key=True)
    compatibility: Mapped[list[dict]] = mapped_column(JSON, default=list)
    growth_rules: Mapped[list[dict]] = mapped_column(JSON, default=list)
    scheduler_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    next_run_at: Mapped[int] = mapped_column(BigInteger, default=0)
    last_result: Mapped[dict] = mapped_column(JSON, default=dict)


class ShopperHandoff(Base):
    __tablename__ = "shopper_handoffs"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("shopping_carts.id", ondelete="CASCADE"), index=True)
    source_shopper_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[int] = mapped_column(BigInteger)
    redeemed: Mapped[bool] = mapped_column(Boolean, default=False)
