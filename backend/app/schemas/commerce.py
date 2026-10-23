"""Strict, bounded public commerce contracts. Prices always originate on the server."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SessionRequest(Contract):
    merchant_id: int = Field(gt=0, le=2147483647, strict=True)


class PolicyRequest(Contract):
    published: bool = False
    max_spend_paise: int = Field(10000000, ge=100, le=100000000, strict=True)
    blocked_categories: list[str] = Field(default_factory=list, max_length=50)
    boosted_product_ids: list[int] = Field(default_factory=list, max_length=100)

    @field_validator("blocked_categories")
    @classmethod
    def categories(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 100 for item in value):
            raise ValueError("Categories must be nonempty and at most 100 characters.")
        return sorted(set(item.strip().casefold() for item in value))

    @field_validator("boosted_product_ids")
    @classmethod
    def product_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value):
            raise ValueError("Product IDs must be positive.")
        return sorted(set(value))


class SearchRequest(Contract):
    query: str = Field(min_length=1, max_length=1000)
    budget_paise: int | None = Field(None, ge=1, le=100000000, strict=True)
    anchor_product_id: int | None = Field(None, gt=0, le=2147483647, strict=True)


class ShoppingIntent(Contract):
    terms: list[str] = Field(max_length=12)
    budget_paise: int | None = Field(None, ge=1, le=100000000)

    @field_validator("terms")
    @classmethod
    def bounded_terms(cls, value: list[str]) -> list[str]:
        if any(not term.strip() or len(term) > 100 for term in value):
            raise ValueError("Invalid search term.")
        return value


class CartLineRequest(Contract):
    product_id: int = Field(gt=0, le=2147483647, strict=True)
    quantity: int = Field(ge=1, le=20, strict=True)


class CartRequest(Contract):
    budget_paise: int = Field(ge=1, le=100000000, strict=True)
    items: list[CartLineRequest] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_products(self) -> "CartRequest":
        if len({line.product_id for line in self.items}) != len(self.items):
            raise ValueError("Combine duplicate product quantities into one line.")
        return self


class Confirmation(Contract):
    confirm: Literal[True]

    @field_validator("confirm", mode="before")
    @classmethod
    def explicit_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit confirmation must be true.")
        return value


class CheckoutRequest(Confirmation):
    mode: Literal["simulation", "razorpay_test"] = "simulation"


class StoreProduct(Contract):
    id: int
    name: str
    description: str
    category: str
    price_paise: int
    available: int


class RankedProduct(StoreProduct):
    score: float
    reasons: list[str]


class SearchResponse(Contract):
    products: list[RankedProduct]
    message: str
    intent_source: Literal["local", "gemini", "local_fallback"]
    budget_paise: int | None
    truncated: bool


class CartLine(Contract):
    product_id: int
    name: str
    quantity: int
    unit_price_paise: int
    subtotal_paise: int


class CartResponse(Contract):
    id: str
    status: str
    budget_paise: int
    total_paise: int
    items: list[CartLine]
    expires_at: int
    checkout_url: str | None


class EventResponse(Contract):
    sequence: int
    event: str
    payload: dict
    created_at: int
    previous_hash: str
    digest: str


class AuditResponse(Contract):
    valid: bool
    events: list[EventResponse]
