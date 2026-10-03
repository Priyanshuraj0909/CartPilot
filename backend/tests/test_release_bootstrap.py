"""Migrations → seed → HTTP demo from an isolated empty database."""
import os
import subprocess
import sys
from pathlib import Path
import httpx
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.api.deps import get_database_session
from app.main import app
from app.core.seed import seed_database
from app.models.merchant import Merchant
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.price_history import PriceHistory
from tests.cross_agent_helpers import four_products

async def test_clean_bootstrap_and_full_http_demo(tmp_path):
    # Percent is valid in paths and encoded DB passwords; Alembic must escape ConfigParser.
    url=f'sqlite+aiosqlite:///{tmp_path / "bootstrap%release.sqlite"}'
    env={**os.environ,'DATABASE_URL':url,'ENVIRONMENT':'test'}
    cwd=Path(__file__).resolve().parents[1]
    for command,revision in [('upgrade','head'),('downgrade','-1'),('upgrade','head')]:
        run=subprocess.run([sys.executable,'-m','alembic',command,revision],cwd=cwd,env=env,capture_output=True,text=True)
        assert run.returncode==0,run.stderr
    engine=create_async_engine(url,echo=False)
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        await seed_database(session)
        counts={model.__tablename__:await session.scalar(select(func.count(model.id))) for model in (Merchant,Product,Inventory,Order,PriceHistory)}
        assert counts['merchants']==1 and counts['products']==25 and counts['orders']==110
        assert counts['inventory']==25 and counts['price_history']>0
        await seed_database(session)
        assert await session.scalar(select(func.count(Order.id)))==110
        scope=await four_products(session)
        async def override(): yield session
        app.dependency_overrides[get_database_session]=override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://release') as client:
                assert (await client.get('/health')).json()=={'status':'ok'}
                catalog=(await client.get(f"/api/v1/products?merchant_id={scope['merchant']}")).json()
                assert catalog['total_products']>=4
                recs={}
                for agent,pid in [('pricing',scope['products'][0]),('restock',scope['products'][0]),('promotion',scope['products'][1]),('listing',scope['products'][2])]:
                    response=await client.post(f'/api/v1/{agent}/recommend',json={'product_id':pid,'merchant_id':scope['merchant']})
                    assert response.status_code==200;recs[agent]=response.json()
                plan=await client.post('/api/v1/orchestrate',json={'merchant_id':scope['merchant'],'goal':'balanced_growth','product_ids':scope['products']})
                assert plan.status_code==200 and plan.json()['products_analyzed']==4
                assert plan.json()['prioritized_actions'][0]['agent']=='restock'
                assert plan.json()['recommendation_relationships']
                created=await client.post('/api/v1/actions',json={'merchant_id':scope['merchant'],'agent':'pricing','recommendation':recs['pricing']})
                assert created.json()['status']=='awaiting_approval';aid=created.json()['id']
                decision={'merchant_id':scope['merchant'],'actor':'release-demo'}
                assert (await client.post(f'/api/v1/actions/{aid}/execute',json={**decision,'confirm':True})).status_code==409
                assert (await client.post(f'/api/v1/actions/{aid}/approve',json=decision)).json()['status']=='approved'
                executed=await client.post(f'/api/v1/actions/{aid}/execute',json={**decision,'confirm':True})
                assert executed.json()['status']=='executed'
                repeat=await client.post(f'/api/v1/actions/{aid}/execute',json={**decision,'confirm':True})
                assert repeat.json()['executed_at']==executed.json()['executed_at']
                history=await client.get(f"/api/v1/action-history?merchant_id={scope['merchant']}")
                assert any(event['event_type']=='execution_completed' for event in history.json())
                # A typed yet unsafe proposal must be policy-blocked, never silently adjusted.
                unsafe={**recs['pricing'],'recommended_price':float(recs['pricing']['current_price'])*1.5,'price_change_percent':50}
                blocked=await client.post('/api/v1/actions',json={'merchant_id':scope['merchant'],'agent':'pricing','recommendation':unsafe})
                assert blocked.json()['status']=='failed' and not blocked.json()['policy']['is_valid']
        finally:
            app.dependency_overrides.clear()
    await engine.dispose()
