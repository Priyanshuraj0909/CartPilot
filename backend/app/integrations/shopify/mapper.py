"""Pure conversions preserve external IDs, money precision and inventory semantics."""
from dataclasses import dataclass
from decimal import Decimal
from app.integrations.shopify.schemas import Variant, InventoryItem, SourceOrder

@dataclass(frozen=True)
class InventoryProjection:
    quantity: int
    reserved: int
    unavailable: int
    snapshot: dict


def product_fields(variant: Variant) -> dict:
    parent=variant.product
    name=parent.title if variant.title=='Default Title' else f'{parent.title} — {variant.title}'
    return {'name':name[:255],'description':parent.description or None,'category':parent.productType[:100] or 'Uncategorized',
        'selling_price':variant.price,'cost_price':None,'source':'shopify','status':parent.status.lower(),'created_at':parent.createdAt}


def internal_sku(variant: Variant) -> str:
    return variant.sku if variant.sku and len(variant.sku)<=100 else f'SHOPIFY-{variant.id.rsplit("/",1)[1]}'


def project_inventory(item: InventoryItem) -> InventoryProjection | None:
    if not item.tracked: return None
    physical=reserved=unavailable=0;seen=set();raw=[]
    for level in item.inventoryLevels:
        if level.location.id in seen: raise ValueError('Duplicate inventory location.')
        seen.add(level.location.id)
        values={q.name:q.quantity for q in level.quantities}
        if len(values)!=len(level.quantities): raise ValueError('Duplicate quantity states.')
        raw.append({'level_id':level.id,'location_id':level.location.id,'active':level.location.isActive and level.isActive,'quantities':values})
        if not level.location.isActive or not level.isActive: continue
        if not {'on_hand','available','committed','reserved'}<=values.keys(): raise ValueError('Inventory quantity states are incomplete.')
        # Negative stock/overselling cannot be represented safely by current local models.
        if any(values[name]<0 for name in ('on_hand','available','committed','reserved')): raise ValueError('Negative stock requires merchant reconciliation.')
        held=values['committed']+values['reserved']
        other=values['on_hand']-values['available']-held
        if other<0: raise ValueError('Inventory states do not reconcile.')
        physical+=values['on_hand'];reserved+=held;unavailable+=other
    if max(physical,reserved,unavailable)>2147483647:
        raise ValueError('Aggregated inventory exceeds local integer capacity.')
    return InventoryProjection(physical,reserved,unavailable,{'locations':raw,'tracked':True})


def order_status(order: SourceOrder) -> tuple[str, bool]:
    if order.cancelledAt is not None or order.displayFinancialStatus in ('REFUNDED','VOIDED','EXPIRED'):
        return 'cancelled',False
    if order.displayFinancialStatus not in ('PENDING','AUTHORIZED','PARTIALLY_PAID','PAID','PARTIALLY_REFUNDED'):
        return 'cancelled',True # Unknown financial state must not become positive sales evidence.
    fulfillment=order.displayFulfillmentStatus
    if fulfillment=='FULFILLED': return 'shipped',False
    if fulfillment in ('PARTIALLY_FULFILLED','UNFULFILLED','IN_PROGRESS','ON_HOLD','PENDING_FULFILLMENT','SCHEDULED','REQUEST_DECLINED','RESTOCKED'):
        return ('confirmed' if order.displayFinancialStatus in ('PAID','PARTIALLY_PAID','PARTIALLY_REFUNDED') else 'pending'),False
    return 'cancelled',True
