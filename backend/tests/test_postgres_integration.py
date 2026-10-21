"""Opt-in integration checks against a migrated disposable PostgreSQL database.

Only the exact database name cartpilot_ci is accepted. Never target store data.
"""
import asyncio
import hashlib
import os
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.audit_log import AuditLog
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models import Base
from app.services.actions import workflow
from app.services.auth_limits import record_attempt
from tests.test_actions import setup_action


@pytest.fixture
async def postgres_factory():
    url = os.environ.get("CARTPILOT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set CARTPILOT_TEST_POSTGRES_URL to a disposable migrated cartpilot_ci database.")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or parsed.database != "cartpilot_ci":
        pytest.fail("PostgreSQL integration tests require the disposable cartpilot_ci database.")
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "16_reliability"
            # The accepted database is explicitly disposable; retain its migrated schema.
            for table in reversed(Base.metadata.sorted_tables):
                await connection.execute(table.delete())
        yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    finally:
        await engine.dispose()


async def test_concurrent_auth_budget_is_atomic(postgres_factory):
    key = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    async def attempt():
        async with postgres_factory() as session:
            retry = await record_attempt(session, key, 3, 1000, 900)
            await session.commit()
            return retry
    results = await asyncio.gather(*(attempt() for _ in range(12)))
    assert results.count(0) == 3
    assert results.count(900) == 9


async def test_concurrent_execution_changes_price_once(postgres_factory):
    async with postgres_factory() as session:
        scope, product_id, created, decision, _ = await setup_action(session)
        await workflow.decide_action(session, created.id, decision, True)
    async def execute():
        async with postgres_factory() as session:
            return await workflow.execute_action(session, created.id, decision)
    results = await asyncio.gather(execute(), execute())
    assert all(result.status == "executed" for result in results)
    assert results[0].executed_at == results[1].executed_at
    async with postgres_factory() as session:
        assert await session.scalar(select(func.count(PriceHistory.id)).where(PriceHistory.product_id == product_id)) == 1
        assert await session.scalar(select(func.count(AuditLog.id)).where(AuditLog.entity_type == "action", AuditLog.entity_id == str(created.id), AuditLog.event_type == "execution_completed")) == 1
        assert str(await session.scalar(select(Product.selling_price).where(Product.id == product_id))) == "1048.95"
