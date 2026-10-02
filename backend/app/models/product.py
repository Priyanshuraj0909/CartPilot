"""Product model representing catalog items."""

from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.merchant import Merchant
    from app.models.inventory import Inventory
    from app.models.order_item import OrderItem
    from app.models.price_history import PriceHistory
    from app.models.recommendation import Recommendation


class Product(Base, TimestampMixin):
    """Product catalog item belonging to a merchant."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("merchant_id", "sku", name="uq_merchant_sku"),
        CheckConstraint("cost_price >= 0", name="chk_product_cost_price_non_negative"),
        CheckConstraint("selling_price >= 0", name="chk_product_selling_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False, index=True)

    # Relationships
    merchant: Mapped["Merchant"] = relationship("Merchant", back_populates="products")
    inventory: Mapped[Optional["Inventory"]] = relationship(
        "Inventory",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )
    order_items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    price_history: Mapped[List["PriceHistory"]] = relationship(
        "PriceHistory",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="desc(PriceHistory.changed_at)",
    )
    recommendations: Mapped[List["Recommendation"]] = relationship(
        "Recommendation",
        back_populates="product",
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, sku='{self.sku}', name='{self.name}', price={self.selling_price})>"
