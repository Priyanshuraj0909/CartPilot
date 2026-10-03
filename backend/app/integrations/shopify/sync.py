"""Independent, idempotent local import units. Never sends merchant writes to Shopify."""
import hashlib
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings
from app.models.shopify import ShopifyConnection, ExternalProductMapping, ExternalOrderMapping
from app.models.merchant import Merchant
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.integrations.shopify.client import ShopifyClient, ShopifyError
from app.integrations.shopify.schemas import Variant, InventoryItem, SourceOrder, SyncRequest, ShopifySyncResult, SyncError
from app.integrations.shopify.mapper import product_fields, internal_sku, project_inventory, order_status

logger=logging.getLogger(__name__)

def utcnow() -> datetime: return datetime.now(timezone.utc)

async def require_binding(session: AsyncSession, config: Settings, merchant_id: int) -> None:
    if config.SHOPIFY_MERCHANT_ID!=merchant_id:
        raise ShopifyError('merchant_scope','Shopify is not configured for the selected merchant.',403)
    if await session.get(Merchant,merchant_id) is None:
        raise ShopifyError('merchant_missing','Merchant not found.',404)

async def connection_record(session: AsyncSession, config: Settings) -> ShopifyConnection:
    record=await session.scalar(select(ShopifyConnection).where(ShopifyConnection.merchant_id==config.SHOPIFY_MERCHANT_ID))
    if record and record.store_domain!=config.SHOPIFY_STORE_DOMAIN:
        raise ShopifyError('store_binding','This merchant is already bound to a different Shopify store. Use a separate merchant.',409)
    if record is None:
        record=ShopifyConnection(merchant_id=config.SHOPIFY_MERCHANT_ID,store_domain=config.SHOPIFY_STORE_DOMAIN)
        session.add(record)
        try: await session.commit()
        except IntegrityError:
            await session.rollback();raise ShopifyError('store_binding','Store binding is already claimed; refresh and verify merchant configuration.',409) from None
    return record

class ShopifySyncService:
    def __init__(self, client: ShopifyClient): self.client=client

    async def upsert_variant(self, session: AsyncSession, connection_id: int, source: Variant) -> str:
        mapping=await session.scalar(select(ExternalProductMapping).where(ExternalProductMapping.connection_id==connection_id,ExternalProductMapping.external_variant_id==source.id))
        created=mapping is None
        if created:
            sku=internal_sku(source)
            merchant_id=self.client.config.SHOPIFY_MERCHANT_ID
            collision=await session.scalar(select(Product.id).where(Product.merchant_id==merchant_id,Product.sku==sku))
            if collision: sku=f'SHOPIFY-{source.id.rsplit("/",1)[1]}'
            if await session.scalar(select(Product.id).where(Product.merchant_id==merchant_id,Product.sku==sku)):
                sku='SF-'+hashlib.sha256(source.id.encode()).hexdigest()[:32]
            product=Product(merchant_id=merchant_id,sku=sku,**product_fields(source));session.add(product);await session.flush()
            mapping=ExternalProductMapping(connection_id=connection_id,product_id=product.id,external_variant_id=source.id,
                external_product_id=source.product.id,inventory_item_id=source.inventoryItem.id,source_updated_at=source.product.updatedAt,last_synced_at=utcnow())
            session.add(mapping)
        else:
            product=await session.get(Product,mapping.product_id)
            if product is None or product.merchant_id!=self.client.config.SHOPIFY_MERCHANT_ID or product.source!='shopify':
                raise ValueError('Product mapping ownership is invalid.')
            for name,value in product_fields(source).items(): setattr(product,name,value)
        mapping.external_sku=source.sku or None;mapping.external_product_id=source.product.id
        mapping.inventory_item_id=source.inventoryItem.id;mapping.source_updated_at=source.product.updatedAt;mapping.last_synced_at=utcnow()
        await session.commit()
        return 'products_created' if created else 'products_updated'

    async def upsert_inventory(self, session: AsyncSession, mapping_id: int, source: InventoryItem, currency: str) -> None:
        mapping=await session.get(ExternalProductMapping,mapping_id)
        if source.id!=mapping.inventory_item_id: raise ValueError('Inventory identity mismatch.')
        product=await session.get(Product,mapping.product_id)
        if product.merchant_id!=self.client.config.SHOPIFY_MERCHANT_ID: raise ValueError('Inventory ownership mismatch.')
        if source.unitCost and source.unitCost.currencyCode!=currency: raise ValueError('Cost currency does not match shop currency.')
        product.cost_price=source.unitCost.amount if source.unitCost else None
        projection=project_inventory(source)
        inventory=await session.scalar(select(Inventory).where(Inventory.product_id==product.id))
        if projection is None:
            if inventory: await session.delete(inventory)
            mapping.inventory_snapshot={'tracked':False,'locations':[]}
        else:
            if inventory is None:
                inventory=Inventory(product_id=product.id,reorder_point=10,reorder_quantity=50);session.add(inventory)
            inventory.quantity=projection.quantity;inventory.reserved_quantity=projection.reserved;inventory.unavailable_quantity=projection.unavailable
            mapping.inventory_snapshot=projection.snapshot
        mapping.inventory_synced_at=utcnow();await session.commit()

    async def invalidate_inventory(self, session: AsyncSession, mapping_id: int) -> None:
        # Unknown current stock must not be represented as confirmed sellable inventory.
        mapping=await session.get(ExternalProductMapping,mapping_id)
        product=await session.get(Product,mapping.product_id);product.cost_price=None
        await session.execute(delete(Inventory).where(Inventory.product_id==product.id))
        mapping.inventory_snapshot={'status':'unavailable','tracked':None};mapping.inventory_synced_at=None
        await session.commit()

    async def upsert_order(self, session: AsyncSession, connection_id: int, source: SourceOrder, currency: str) -> tuple[str, bool, bool]:
        if source.currentTotalPriceSet.shopMoney.currencyCode!=currency: raise ValueError('Order currency does not match shop currency.')
        ids=[line.id for line in source.lineItems]
        if len(ids)!=len(set(ids)): raise ValueError('Duplicate Shopify order lines.')
        local_lines=[];unmapped=False
        for line in source.lineItems:
            if line.currentQuantity>line.quantity: raise ValueError('Current order quantity exceeds original quantity.')
            if line.currentQuantity==0: continue
            money=line.discountedUnitPriceAfterAllDiscountsSet.shopMoney
            if money.currencyCode!=currency: raise ValueError('Order line currency does not match shop currency.')
            mapping=await session.scalar(select(ExternalProductMapping).where(ExternalProductMapping.connection_id==connection_id,ExternalProductMapping.external_variant_id==line.variant.id)) if line.variant else None
            if mapping is None: unmapped=True;continue
            product=await session.get(Product,mapping.product_id)
            if product.merchant_id!=self.client.config.SHOPIFY_MERCHANT_ID: raise ValueError('Order line ownership mismatch.')
            if money.amount*line.currentQuantity > Decimal("99999999.99"):
                raise ValueError('Order line subtotal exceeds local monetary precision.')
            local_lines.append({'product_id':mapping.product_id,'quantity':line.currentQuantity,'unit_price':money.amount.quantize(Decimal('.01'),rounding=ROUND_HALF_UP),'subtotal':(money.amount*line.currentQuantity).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)})
        # Do not import an incomplete order as positive sales evidence.
        if unmapped:
            previous=await session.scalar(select(ExternalOrderMapping).where(ExternalOrderMapping.connection_id==connection_id,ExternalOrderMapping.external_order_id==source.id))
            if previous:
                old=await session.get(Order,previous.order_id)
                old.status='cancelled'
                await session.execute(delete(OrderItem).where(OrderItem.order_id==old.id))
                previous.last_synced_at=utcnow()
                await session.commit()
            return 'orders_skipped',True,False
        mapped=await session.scalar(select(ExternalOrderMapping).where(ExternalOrderMapping.connection_id==connection_id,ExternalOrderMapping.external_order_id==source.id))
        created=mapped is None
        status,unknown=order_status(source)
        if created:
            order=Order(merchant_id=self.client.config.SHOPIFY_MERCHANT_ID,order_number=f'SHOPIFY-{connection_id}-{source.id.rsplit("/",1)[1]}',
                status=status,total_amount=source.currentTotalPriceSet.shopMoney.amount,ordered_at=source.createdAt,customer_reference=None)
            session.add(order);await session.flush()
            mapped=ExternalOrderMapping(connection_id=connection_id,order_id=order.id,external_order_id=source.id,last_synced_at=utcnow());session.add(mapped)
        else:
            order=await session.get(Order,mapped.order_id)
            if order.merchant_id!=self.client.config.SHOPIFY_MERCHANT_ID: raise ValueError('Order ownership mismatch.')
            order.status=status;order.total_amount=source.currentTotalPriceSet.shopMoney.amount;order.ordered_at=source.createdAt;order.customer_reference=None
            await session.execute(delete(OrderItem).where(OrderItem.order_id==order.id))
        session.add_all([OrderItem(order_id=order.id,**line) for line in local_lines])
        mapped.last_synced_at=utcnow();await session.commit()
        return 'orders_created' if created else 'orders_updated',False,unknown

    async def sync(self, session: AsyncSession, request: SyncRequest) -> ShopifySyncResult:
        config=self.client.config
        await require_binding(session,config,request.merchant_id)
        if not any((request.products,request.inventory,request.orders)):
            raise ShopifyError('empty_sync','Select at least one synchronization stage.',422)
        connection=await connection_record(session,config);connection_id=connection.id
        result=ShopifySyncResult(status='started',started_at=utcnow())
        claimed=await session.execute(update(ShopifyConnection).where(ShopifyConnection.id==connection_id,ShopifyConnection.sync_in_progress.is_(False))
            .values(sync_in_progress=True,last_sync=result.model_dump(mode='json')).execution_options(synchronize_session=False))
        if claimed.rowcount!=1:
            await session.rollback();raise ShopifyError('sync_busy','A Shopify sync is already running. Wait before starting another.',409)
        await session.commit()
        logger.info('shopify_sync_started merchant_id=%s',request.merchant_id)
        successful=0
        def error(stage,exc,external_id=None):
            message=str(exc) if isinstance(exc,ShopifyError) else 'Source data or local storage could not be safely imported.'
            result.errors.append(SyncError(stage=stage,code=exc.code if isinstance(exc,ShopifyError) else 'invalid_record',message=message,external_id=external_id))
        try:
            try:
                shop=await self.client.connection();currency=shop['currency']
                connection=await session.get(ShopifyConnection,connection_id)
                if connection.currency and connection.currency!=currency:
                    raise ShopifyError('currency_changed','Shop currency changed; use a separate merchant cache to avoid mixing currencies.',409)
                connection.currency=currency;await session.commit()
            except ShopifyError as exc:
                error('connection',exc);result.status='failed';return result
            if request.products:
                try:
                    async for page in self.client.variants():
                        for raw in page:
                            try:
                                source=Variant.model_validate(raw);field=await self.upsert_variant(session,connection_id,source)
                                setattr(result,field,getattr(result,field)+1);successful+=1
                            except (ValueError,SQLAlchemyError) as exc:
                                await session.rollback();error('products',exc)
                except ShopifyError as exc: error('products',exc)
            if request.inventory:
                mappings=(await session.execute(select(ExternalProductMapping.id,ExternalProductMapping.inventory_item_id).where(ExternalProductMapping.connection_id==connection_id))).all()
                for mapping_id,item_id in mappings:
                    try:
                        source=InventoryItem.model_validate(await self.client.inventory(item_id))
                        await self.upsert_inventory(session,mapping_id,source,currency);result.inventory_updated+=1;successful+=1
                        if source.unitCost is None: result.warnings.append('Cost data is unavailable for one or more variants; pricing and promotion will decline margin-dependent proposals.')
                    except (ShopifyError,ValueError,SQLAlchemyError) as exc:
                        await session.rollback();error('inventory',exc,item_id)
                        try: await self.invalidate_inventory(session,mapping_id)
                        except SQLAlchemyError:
                            await session.rollback();error('storage',ShopifyError('storage','Could not mark inventory unavailable. Review cache freshness before analysis.'))
            if request.orders:
                try:
                    async for page in self.client.orders():
                        for raw in page:
                            try:
                                source=SourceOrder.model_validate(raw);field,unmapped,unknown=await self.upsert_order(session,connection_id,source,currency)
                                setattr(result,field,getattr(result,field)+1)
                                if unmapped: error('orders',ShopifyError('unmapped_lines','Order was skipped because a variant is missing or unmapped.'),source.id)
                                else: successful+=1
                                if unknown: error('orders',ShopifyError('unknown_status','Unknown order status was excluded from positive sales evidence.'),source.id)
                            except (ValueError,SQLAlchemyError) as exc:
                                await session.rollback();error('orders',exc)
                except ShopifyError as exc: error('orders',exc)
            result.status='partial' if result.errors and successful else 'failed' if result.errors else 'completed'
            return result
        except SQLAlchemyError as exc:
            await session.rollback();error('storage',exc)
            result.status='partial' if successful else 'failed'
            return result
        finally:
            if result.status=='started':
                result.status='failed'
                error('storage',ShopifyError('interrupted','Synchronization was interrupted; completed records remain cached.'))
            result.completed_at=utcnow();result.warnings=list(dict.fromkeys(result.warnings))
            await session.execute(update(ShopifyConnection).where(ShopifyConnection.id==connection_id)
                .values(sync_in_progress=False,last_sync=result.model_dump(mode='json')).execution_options(synchronize_session=False))
            await session.commit()
            logger.info('shopify_sync_finished merchant_id=%s status=%s',request.merchant_id,result.status)
