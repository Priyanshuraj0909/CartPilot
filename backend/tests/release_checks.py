"""Isolated API performance/seed smoke report, not a production load benchmark."""
import asyncio
import json
import statistics
from time import perf_counter
from sqlalchemy import event,select,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from httpx import AsyncClient,ASGITransport
from app.models.base import Base
from app.models.merchant import Merchant
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.price_history import PriceHistory
from app.main import app
from app.api.deps import get_database_session
from app.core.seed import seed_database

async def main():
    engine=create_async_engine('sqlite+aiosqlite:///:memory:',echo=False)
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        merchant,products,_=await seed_database(session)
        counts={model.__tablename__:await session.scalar(select(func.count(model.id))) for model in (Merchant,Product,Inventory,Order,PriceHistory)}
        queries=[]
        def capture(*args): queries.append(args[2])
        event.listen(engine.sync_engine,'before_cursor_execute',capture)
        async def override(): yield session
        app.dependency_overrides[get_database_session]=override
        measurements={}
        try:
            async with AsyncClient(transport=ASGITransport(app=app),base_url='http://release') as client:
                for name,path,body in [
                    ('products_25',f'/api/v1/products?merchant_id={merchant.id}',None),
                    ('inventory_25',f'/api/v1/inventory?merchant_id={merchant.id}',None),
                    ('pricing_single','/api/v1/pricing/recommend',{'merchant_id':merchant.id,'product_id':products[0].id}),
                    ('balanced_growth_25','/api/v1/orchestrate',{'merchant_id':merchant.id,'goal':'balanced_growth'}),
                ]:
                    durations=[];query_counts=[]
                    for _ in range(3):
                        queries.clear();start=perf_counter()
                        response=await client.get(path) if body is None else await client.post(path,json=body)
                        durations.append((perf_counter()-start)*1000);query_counts.append(len(queries))
                        assert response.status_code==200
                    measurements[name]={'median_ms':round(statistics.median(durations),2),'max_ms':round(max(durations),2),'query_counts':query_counts}
        finally:
            app.dependency_overrides.clear()
            event.remove(engine.sync_engine,'before_cursor_execute',capture)
        print(json.dumps({'environment':'isolated in-memory SQLite; ASGI; 3 samples; not a load test','seed_counts':counts,'performance':measurements},indent=2))
    await engine.dispose()

if __name__=='__main__': asyncio.run(main())
