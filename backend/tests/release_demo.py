"""Explicit offline browser-demo server. Requires a disposable SQLite URL."""
import asyncio
import os
import uvicorn
from app.main import app
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.seed import seed_database
from app.models.merchant import Merchant
from tests.cross_agent_helpers import four_products
from tests.shopify_helpers import ShopifyFixture
from app.api.v1 import shopify

async def prepare():
    # Never initialize the developer/production database through this demo helper.
    if settings.ENVIRONMENT!='test' or not settings.DATABASE_URL.startswith('sqlite+aiosqlite:'):
        raise RuntimeError('Release demo requires ENVIRONMENT=test and disposable SQLite DATABASE_URL.')
    async with AsyncSessionLocal() as session:
        await seed_database(session)
        scope=await four_products(session)
        merchant=await session.get(Merchant,scope['merchant']);merchant.store_name='Four-product Demo'
        merchant=Merchant(name='Offline Shopify',store_name='Shopify Offline Demo',email='shopify-offline@example.test')
        session.add(merchant);await session.commit()
        source=ShopifyFixture(merchant.id)
        settings.SHOPIFY_STORE_DOMAIN=source.config.SHOPIFY_STORE_DOMAIN
        settings.SHOPIFY_ACCESS_TOKEN=source.config.SHOPIFY_ACCESS_TOKEN
        settings.SHOPIFY_MERCHANT_ID=merchant.id
        shopify.build_client=source.client

if __name__=='__main__':
    asyncio.run(prepare())
    uvicorn.run(app,host='127.0.0.1',port=int(os.environ.get('RELEASE_DEMO_PORT','8012')))
