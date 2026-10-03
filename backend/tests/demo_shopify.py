"""Offline Phase 11 demo: mocked HTTP, isolated SQLite, normal agents/orchestrator."""
import asyncio
import json
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models.base import Base
from app.models.merchant import Merchant
from app.models.product import Product
from app.schemas.orchestration import OrchestrationRequest
from app.agents.orchestrator import MasterOrchestrator
from app.integrations.shopify.schemas import SyncRequest
from app.integrations.shopify.sync import ShopifySyncService
from tests.shopify_helpers import ShopifyFixture

async def main():
    logging.getLogger('httpx').setLevel(logging.WARNING)
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        merchant=Merchant(name='Offline Shopify Demo',email='offline@example.test',store_name='Offline Shopify Demo')
        session.add(merchant);await session.commit()
        source=ShopifyFixture(merchant.id)
        service=ShopifySyncService(source.client());request=SyncRequest(merchant_id=merchant.id)
        first=await service.sync(session,request)
        second=await service.sync(session,request)
        plan=await MasterOrchestrator().analyze(OrchestrationRequest(merchant_id=merchant.id,goal='balanced_growth'),session)
        products=(await session.scalars(select(Product).order_by(Product.id))).all()
        source.inventory_failure=True
        failure=await service.sync(session,request)
        print(json.dumps({'demo':'offline mocked Shopify HTTP; no real store accessed','mode':'read_only',
            'first_sync':first.model_dump(mode='json'),'repeat_sync':second.model_dump(mode='json'),
            'products':[{'id':p.id,'sku':p.sku,'name':p.name,'source':p.source} for p in products],
            'balanced_growth':plan.model_dump(mode='json'),'partial_failure':failure.model_dump(mode='json'),
            'external_operations':sorted({call['query'].split('(')[0].split('{')[0].strip() for call in source.calls}),
            'shopify_mutations':0},indent=2))
    await engine.dispose()

if __name__=='__main__': asyncio.run(main())
