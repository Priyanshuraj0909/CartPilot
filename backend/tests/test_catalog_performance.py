"""Keep catalog query counts bounded without changing store calculations."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.services.pricing.signals import aggregate_sales_snapshots
from app.services.store.catalog import get_catalog


@pytest.mark.asyncio
async def test_catalog_page_uses_constant_query_budget(seeded_session):
    statements = []
    engine = seeded_session.bind.sync_engine
    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", record)
    try:
        snapshot = await get_catalog(seeded_session, 1)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(snapshot.products) == 25
    assert len(statements) <= 9, f"Catalog performed {len(statements)} queries"
    assert snapshot.total_products == 25
    assert sum(p.recent_units for p in snapshot.products) > 0


@pytest.mark.asyncio
async def test_batch_empty_page_and_missing_sales(seeded_session):
    now = datetime.now(timezone.utc)
    assert await aggregate_sales_snapshots(seeded_session, 1, [], 14, now) == {}
    result = await aggregate_sales_snapshots(seeded_session, 1, [999999], 14, now)
    assert result[999999].units == 0
    assert result[999999].revenue == Decimal("0")
    assert (await get_catalog(seeded_session, 1, offset=100)).products == []


@pytest.mark.asyncio
async def test_batch_invalid_lookback(seeded_session):
    with pytest.raises(ValueError, match="positive"):
        await aggregate_sales_snapshots(seeded_session, 1, [1], 0, datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_batch_excludes_other_merchants(seeded_session):
    result = await aggregate_sales_snapshots(
        seeded_session, 999999, [1], 14, datetime.now(timezone.utc)
    )
    assert result[1].units == 0
    assert result[1].lifetime_orders == 0
    assert result[1].price_changes == 0
