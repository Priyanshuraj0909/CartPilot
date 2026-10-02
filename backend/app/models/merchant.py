"""Merchant model representing store owners."""

from typing import TYPE_CHECKING, List
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.order import Order
    from app.models.recommendation import Recommendation
    from app.models.audit_log import AuditLog


class Merchant(Base, TimestampMixin):
    """Merchant entity owning products, inventory, orders, and storefront settings."""

    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    products: Mapped[List["Product"]] = relationship(
        "Product",
        back_populates="merchant",
        cascade="all, delete-orphan",
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order",
        back_populates="merchant",
        cascade="all, delete-orphan",
    )
    recommendations: Mapped[List["Recommendation"]] = relationship(
        "Recommendation",
        back_populates="merchant",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="merchant",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Merchant(id={self.id}, store_name='{self.store_name}', email='{self.email}')>"
