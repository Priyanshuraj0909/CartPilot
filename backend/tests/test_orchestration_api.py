"""Orchestration endpoint validation, tenant isolation, and partial responses."""
import pytest
from sqlalchemy import select
from app.api.deps import get_database_session
from app.main import app
from app.models.inventory import Inventory
from tests.orchestration_helpers import make_store


@pytest.fixture
async def orchestration_session(db_session):
    async def override():
        yield db_session
    app.dependency_overrides[get_database_session] = override
    try:
        yield db_session
    finally:
        app.dependency_overrides.pop(get_database_session, None)


@pytest.mark.asyncio
async def test_api_demo(async_client, orchestration_session):
    store = await make_store(orchestration_session)
    payload = {"merchant_id": store["merchant"], "goal": "Increase revenue while avoiding stockouts", "product_ids": [store["low"]]}
    response = await async_client.post("/api/v1/orchestrate", json=payload)
    assert response.status_code == 200
    plan = response.json()
    assert plan["complete"] and plan["approval_required"]
    assert plan["recommendations"][0]["recommended_quantity"] == 67
    assert plan["recommendations"][1]["action"] == "review_price_change"
    assert plan["overall_risk"] == "high" and plan["relationships"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,status", [("merchant", 404), ("product", 404), ("foreign", 403)])
async def test_scope_errors(async_client, orchestration_session, kind, status):
    store = await make_store(orchestration_session)
    payload = {"merchant_id": 9999 if kind == "merchant" else store["merchant"], "goal": "Optimize pricing",
               "product_ids": [store["foreign"] if kind == "foreign" else 9999 if kind == "product" else store["low"]]}
    response = await async_client.post("/api/v1/orchestrate", json=payload)
    assert response.status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize("patch", [{"goal": "Launch campaigns"}, {"product_ids": []}, {"product_ids": [1, 1]},
    {"merchant_id": True}, {"product_ids": ["1"]}, {"constraints": {"auto_approve": True}}])
async def test_invalid_requests(async_client, orchestration_session, patch):
    payload = {"merchant_id": 1, "goal": "Optimize pricing", "product_ids": [1]}
    payload.update(patch)
    response = await async_client.post("/api/v1/orchestrate", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_explicit_products_required(async_client, orchestration_session):
    response = await async_client.post("/api/v1/orchestrate", json={"merchant_id": 1, "goal": "Avoid stockouts"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_inventory_returns_partial_plan(async_client, orchestration_session):
    store = await make_store(orchestration_session)
    inventory = (await orchestration_session.execute(select(Inventory).where(Inventory.product_id == store["low"]))).scalar_one()
    await orchestration_session.delete(inventory)
    await orchestration_session.commit()
    orchestration_session.expire_all()
    response = await async_client.post("/api/v1/orchestrate", json={"merchant_id": store["merchant"],
        "goal": "Increase revenue while avoiding stockouts", "product_ids": [store["low"]]})
    assert response.status_code == 200
    plan = response.json()
    assert not plan["complete"] and plan["overall_risk"] == "high"
    assert plan["agent_results"][0]["success"] and not plan["agent_results"][1]["success"]
