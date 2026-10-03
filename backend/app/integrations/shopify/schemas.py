"""Validate only analysis data: no customer identity fields are requested or retained."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class SourceModel(BaseModel):
    model_config=ConfigDict(extra='ignore',allow_inf_nan=False)

class Money(SourceModel):
    amount: Decimal=Field(ge=0,max_digits=10,decimal_places=2)
    currencyCode: str=Field(pattern=r'^[A-Z]{3}$')

class MoneySet(SourceModel):
    shopMoney: Money

class ParentProduct(SourceModel):
    id: str=Field(pattern=r'^gid://shopify/Product/\d+$')
    title: str=Field(min_length=1)
    description: str=''
    productType: str=''
    status: Literal['ACTIVE','ARCHIVED','DRAFT']
    createdAt: datetime
    updatedAt: datetime
    @field_validator('createdAt','updatedAt')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None: raise ValueError('Shopify timestamps must include a timezone.')
        return value

class ItemIdentity(SourceModel):
    id: str=Field(pattern=r'^gid://shopify/InventoryItem/\d+$')

class Variant(SourceModel):
    id: str=Field(pattern=r'^gid://shopify/ProductVariant/\d+$')
    title: str
    sku: str | None=None
    price: Decimal=Field(ge=0,max_digits=10,decimal_places=2)
    inventoryItem: ItemIdentity
    product: ParentProduct

class Location(SourceModel):
    id: str=Field(pattern=r'^gid://shopify/Location/\d+$')
    isActive: bool=Field(strict=True)

class Quantity(SourceModel):
    name: str
    quantity: int=Field(strict=True)

class Level(SourceModel):
    id: str
    isActive: bool=Field(strict=True)
    location: Location
    quantities: list[Quantity]

class InventoryItem(SourceModel):
    id: str=Field(pattern=r'^gid://shopify/InventoryItem/\d+$')
    tracked: bool=Field(strict=True)
    unitCost: Money | None=None
    inventoryLevels: list[Level]

class VariantIdentity(SourceModel):
    id: str=Field(pattern=r'^gid://shopify/ProductVariant/\d+$')

class UnitMoney(Money):
    # Shopify discounted unit prices can be repeating decimal approximations.
    amount: Decimal = Field(ge=0, le=Decimal("99999999.99"))

class UnitMoneySet(SourceModel):
    shopMoney: UnitMoney

class Line(SourceModel):
    id: str=Field(pattern=r'^gid://shopify/LineItem/\d+$')
    quantity: int=Field(ge=0,le=2147483647,strict=True)
    currentQuantity: int=Field(ge=0,le=2147483647,strict=True)
    variant: VariantIdentity | None=None
    discountedUnitPriceAfterAllDiscountsSet: UnitMoneySet

class SourceOrder(SourceModel):
    id: str=Field(pattern=r'^gid://shopify/Order/\d+$')
    name: str
    createdAt: datetime
    cancelledAt: datetime | None=None
    displayFinancialStatus: str
    displayFulfillmentStatus: str
    currentTotalPriceSet: MoneySet
    lineItems: list[Line]
    @field_validator('createdAt','cancelledAt')
    @classmethod
    def aware(cls,value):
        if value is not None and value.tzinfo is None: raise ValueError('Shopify timestamps must include a timezone.')
        return value

class SyncError(BaseModel):
    stage: Literal['connection','products','inventory','orders','storage']
    code: str
    message: str
    external_id: str | None=None

class ShopifySyncResult(BaseModel):
    mode: Literal['read_only']='read_only'
    status: Literal['started','completed','partial','failed']
    started_at: datetime
    completed_at: datetime | None=None
    products_created: int=0
    products_updated: int=0
    inventory_updated: int=0
    orders_created: int=0
    orders_updated: int=0
    orders_skipped: int=0
    errors: list[SyncError]=Field(default_factory=list)
    warnings: list[str]=Field(default_factory=list)

class SyncRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    merchant_id: int=Field(gt=0,strict=True)
    products: bool=Field(default=True,strict=True)
    inventory: bool=Field(default=True,strict=True)
    orders: bool=Field(default=True,strict=True)

class ConnectionStatus(BaseModel):
    mode: Literal['read_only']='read_only'
    configured: bool
    connected: bool
    store: str | None=None
    currency: str | None=None
    api_version: str
    message: str
    last_sync: ShopifySyncResult | None=None
