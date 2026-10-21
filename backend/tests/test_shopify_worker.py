"""Scheduled sync starts once, survives failures, and closes on cancellation."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.integrations.shopify import worker


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "SHOPIFY_STORE_DOMAIN", "fixture-store.myshopify.com")
    monkeypatch.setattr(settings, "SHOPIFY_ACCESS_TOKEN", SecretStr("fixture-token"))
    monkeypatch.setattr(settings, "SHOPIFY_CLIENT_ID", "")
    monkeypatch.setattr(settings, "SHOPIFY_CLIENT_SECRET", SecretStr(""))
    monkeypatch.setattr(settings, "SHOPIFY_MERCHANT_ID", 1)
    monkeypatch.setattr(settings, "SHOPIFY_AUTO_SYNC_ENABLED", True)


async def test_unconfigured_worker_skips_without_database(monkeypatch):
    monkeypatch.setattr(settings, "SHOPIFY_STORE_DOMAIN", "")
    factory = MagicMock()
    monkeypatch.setattr(worker, "AsyncSessionLocal", factory)
    assert await worker.run_once() == "skipped"
    factory.assert_not_called()


@pytest.mark.parametrize("status", ["completed", "partial", "failed"])
async def test_run_once_reports_sync_status(configured, monkeypatch, status):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=object())
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(worker, "AsyncSessionLocal", lambda: context)
    summary = SimpleNamespace(status=status, products_created=1, products_updated=2, inventory_updated=3, orders_created=4, orders_updated=5, errors=[])
    sync = AsyncMock(return_value=summary)
    monkeypatch.setattr(worker, "ShopifySyncService", lambda _: SimpleNamespace(sync=sync))
    assert await worker.run_once(object()) == status
    assert sync.call_args.args[1].merchant_id == 1


async def test_run_failure_is_sanitized(configured, monkeypatch, caplog):
    def fail():
        raise RuntimeError("private-token")
    monkeypatch.setattr(worker, "AsyncSessionLocal", fail)
    assert await worker.run_once(object()) == "failed"
    assert "private-token" not in caplog.text


async def test_disabled_worker_never_starts(monkeypatch):
    monkeypatch.setattr(settings, "SHOPIFY_AUTO_SYNC_ENABLED", False)
    run = AsyncMock()
    monkeypatch.setattr(worker, "run_once", run)
    await worker.run_forever()
    run.assert_not_called()


async def test_repeats_after_failure_and_closes_on_cancel(configured, monkeypatch):
    run = AsyncMock(side_effect=["failed", "completed"])
    sleeps = []
    async def sleep(interval):
        sleeps.append(interval)
        if len(sleeps) == 2:
            raise asyncio.CancelledError()
    close = AsyncMock()
    monkeypatch.setattr(worker, "run_once", run)
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    monkeypatch.setattr(worker, "close_db_connection", close)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_forever()
    assert run.await_count == 2 and sleeps == [settings.SHOPIFY_AUTO_SYNC_INTERVAL_SECONDS] * 2
    close.assert_awaited_once()
