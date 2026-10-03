"""Run an isolated four-product HTTP demo: python -m tests.demo_cross_agent."""
import asyncio, json
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.api.deps import get_database_session
from app.models.base import Base
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.action import Action
from app.models.recommendation import Recommendation
from app.models.approval import Approval
from tests.cross_agent_helpers import four_products

async def main():
 engine=create_async_engine('sqlite+aiosqlite:///:memory:')
 async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
 factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as session:
  scope=await four_products(session)
  async def override(): yield session
  app.dependency_overrides[get_database_session]=override
  request={'merchant_id':scope['merchant'],'goal':'balanced_growth','product_ids':scope['products']}
  before=(await session.execute(select(Product.id,Product.name,Product.description,Product.selling_price))).all()
  stock=(await session.execute(select(Inventory.product_id,Inventory.quantity))).all()
  async with AsyncClient(transport=ASGITransport(app=app),base_url='http://demo') as client:
   response=await client.post('/api/v1/orchestrate',json=request)
   assert response.status_code==200
   plan=response.json()
   assert before==(await session.execute(select(Product.id,Product.name,Product.description,Product.selling_price))).all()
   assert stock==(await session.execute(select(Inventory.product_id,Inventory.quantity))).all()
   for model in (Action,Recommendation,Approval): assert await session.scalar(select(func.count(model.id)))==0
   output={'request':request,'response':plan,'verification':{'operational_data_unchanged':True,'actions_created_by_analysis':0,'approvals_created_by_analysis':0,'recommendations_persisted_by_analysis':0}}
   print(json.dumps(output,indent=2))
  app.dependency_overrides.clear()
 await engine.dispose()
if __name__ == "__main__":
 asyncio.run(main())
