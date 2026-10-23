"""Shopper capabilities, guarded cart snapshots and append-only application audit."""
from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class CommercePolicy(Base):
    __tablename__ = "commerce_policies"
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), primary_key=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    max_spend_paise: Mapped[int] = mapped_column(BigInteger, default=10000000)
    blocked_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    boosted_product_ids: Mapped[list[int]] = mapped_column(JSON, default=list)


class ShopperSession(Base):
    __tablename__ = "shopper_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[int] = mapped_column(BigInteger)


class ShoppingCart(Base):
    __tablename__ = "shopping_carts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    shopper_hash: Mapped[str] = mapped_column(ForeignKey("shopper_sessions.token_hash", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    budget_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    items: Mapped[list[dict]] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[int] = mapped_column(BigInteger)
    checkout_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    checkout_url: Mapped[str | None] = mapped_column(String(500))


class CommerceEvent(Base):
    __tablename__ = "commerce_events"
    __table_args__ = (UniqueConstraint("cart_id", "sequence", name="uq_commerce_cart_sequence"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("shopping_carts.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(BigInteger)
    previous_hash: Mapped[str] = mapped_column(String(64))
    digest: Mapped[str] = mapped_column(String(64))


class CommerceModel(Base):
    __tablename__ = "commerce_models"
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[int] = mapped_column(BigInteger)
