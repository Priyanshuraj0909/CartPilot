"""Authenticated catalog management and atomic, idempotent sales import."""
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_database_session
from app.api.v1.accounts import current_account
from app.models.account import Account
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.price_history import PriceHistory
from app.models.order import Order
from app.models.order_item import OrderItem

router=APIRouter(tags=['Store management'])

class ProductInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    sku: str=Field(min_length=1,max_length=100)
    name: str=Field(min_length=1,max_length=255)
    category: str=Field(min_length=1,max_length=100)
    description: str | None=Field(None,max_length=5000)
    cost_price: Decimal=Field(ge=0,max_digits=10,decimal_places=2)
    selling_price: Decimal=Field(gt=0,max_digits=10,decimal_places=2)
    quantity: int=Field(ge=0,le=1000000,strict=True)
    @model_validator(mode='after')
    def margin(self):
        if self.selling_price < self.cost_price:
            raise ValueError('Selling price must cover cost.')
        return self

async def owned(session: AsyncSession, account: Account, product_id: int) -> Product:
    product=await session.scalar(select(Product).where(Product.id==product_id).with_for_update())
    if product is None or product.merchant_id != account.merchant_id:
        raise HTTPException(404,'Product not found.')
    if product.source != 'local':
        raise HTTPException(409,'Manage externally sourced products in their source store.')
    return product

async def save(session: AsyncSession):
    try: await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409,'SKU or sales reference already exists.')

@router.post('/products',status_code=201)
async def create(body: ProductInput, account: Account=Depends(current_account), session: AsyncSession=Depends(get_database_session)):
    values=body.model_dump();quantity=values.pop('quantity')
    product=Product(merchant_id=account.merchant_id,**values,status='active',source='local')
    session.add(product)
    try: await session.flush()
    except IntegrityError:
        await session.rollback();raise HTTPException(409,'SKU already exists.')
    session.add(Inventory(product_id=product.id,quantity=quantity,reserved_quantity=0,unavailable_quantity=0,reorder_point=10,reorder_quantity=50))
    session.add(PriceHistory(product_id=product.id,old_price=body.selling_price,new_price=body.selling_price,reason='Merchant created product'))
    await save(session)
    return {'id':product.id}

@router.put('/products/{product_id}')
async def edit(product_id: int, body: ProductInput, account: Account=Depends(current_account), session: AsyncSession=Depends(get_database_session)):
    product=await owned(session,account,product_id)
    inventory=await session.scalar(select(Inventory).where(Inventory.product_id==product.id))
    if inventory is None or body.quantity < inventory.reserved_quantity+inventory.unavailable_quantity:
        raise HTTPException(409,'Stock cannot be below reserved/unavailable quantities.')
    if body.selling_price != product.selling_price:
        session.add(PriceHistory(product_id=product.id,old_price=product.selling_price,new_price=body.selling_price,reason='Merchant catalog edit'))
    for key,value in body.model_dump(exclude={'quantity'}).items():setattr(product,key,value)
    inventory.quantity=body.quantity
    await save(session)
    return {'id':product.id}

@router.delete('/products/{product_id}')
async def archive(product_id: int, account: Account=Depends(current_account), session: AsyncSession=Depends(get_database_session)):
    product=await owned(session,account,product_id)
    product.status='archived'
    await save(session)
    return {'id':product.id,'status':'archived'}

class Sale(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reference: str=Field(min_length=1,max_length=60,pattern=r'^[A-Za-z0-9_-]+$')
    product_id: int=Field(gt=0,strict=True)
    quantity: int=Field(gt=0,le=100000,strict=True)
    unit_price: Decimal=Field(ge=0,max_digits=10,decimal_places=2)
    ordered_at: datetime
    @model_validator(mode='after')
    def valid_time(self):
        if self.ordered_at.tzinfo is None or self.ordered_at > datetime.now(timezone.utc):
            raise ValueError('Sales dates must be timezone-aware and not in the future.')
        if self.unit_price*self.quantity > Decimal('99999999.99'):
            raise ValueError('Sale total exceeds supported amount.')
        return self

class SalesInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sales: list[Sale]=Field(min_length=1,max_length=500)

@router.post('/sales/import')
async def import_sales(body: SalesInput, account: Account=Depends(current_account), session: AsyncSession=Depends(get_database_session)):
    imported=0;skipped=0
    seen=set()
    for sale in body.sales:
        await owned(session,account,sale.product_id)
        number=f'import-{account.merchant_id}-{sale.reference}'
        if number in seen:raise HTTPException(422,'Duplicate references in upload.')
        seen.add(number)
        old=await session.scalar(select(Order).where(Order.order_number==number))
        if old:
            item=await session.scalar(select(OrderItem).where(OrderItem.order_id==old.id))
            if not item or (item.product_id,item.quantity,item.unit_price,old.ordered_at.replace(tzinfo=timezone.utc)) != (sale.product_id,sale.quantity,sale.unit_price,sale.ordered_at.astimezone(timezone.utc)):
                raise HTTPException(409,'Existing reference has different sale data.')
            skipped+=1;continue
        total=sale.unit_price*sale.quantity
        order=Order(merchant_id=account.merchant_id,order_number=number,status='delivered',total_amount=total,ordered_at=sale.ordered_at)
        session.add(order)
        try: await session.flush()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(409,'Sales reference already exists; retry the import.')
        session.add(OrderItem(order_id=order.id,product_id=sale.product_id,quantity=sale.quantity,unit_price=sale.unit_price,subtotal=total))
        imported+=1
    await save(session)
    return {'imported':imported,'skipped':skipped}

@router.get('/analytics')
async def analytics(account: Account=Depends(current_account),session: AsyncSession=Depends(get_database_session)):
    rows=(await session.execute(select(Product.id,Product.name,func.sum(OrderItem.quantity).label('units'),func.sum(OrderItem.subtotal).label('revenue')).join(OrderItem,OrderItem.product_id==Product.id).join(Order,Order.id==OrderItem.order_id).where(Product.merchant_id==account.merchant_id,Order.merchant_id==account.merchant_id,Order.status.in_(['confirmed','shipped','delivered'])).group_by(Product.id,Product.name).order_by(func.sum(OrderItem.quantity).desc(),Product.id))).all()
    return {'products':[{'id':r.id,'name':r.name,'units':r.units,'revenue':str(r.revenue)} for r in rows], 'total_revenue':str(sum((r.revenue for r in rows),Decimal(0)))}

@router.get('/notifications')
async def notifications(account: Account=Depends(current_account),session: AsyncSession=Depends(get_database_session)):
    rows=(await session.execute(select(Product.name,Inventory.quantity,Inventory.reserved_quantity,Inventory.unavailable_quantity,Inventory.reorder_point).join(Inventory,Inventory.product_id==Product.id).where(Product.merchant_id==account.merchant_id,Product.status=='active'))).all()
    return {'notifications':[{'product':r.name,'message':'Available stock is at or below the reorder point.'} for r in rows if max(0,r.quantity-r.reserved_quantity-r.unavailable_quantity)<=r.reorder_point]}
