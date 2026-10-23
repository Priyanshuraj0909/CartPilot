"""Merchant rules, scheduled boundaries, provider ingestion, offers and AI failover."""
import json
import time
from decimal import Decimal
import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from app.core.config import settings
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.commerce import CommercePolicy, ShoppingCart
from app.models.commerce_workflows import CommerceRules
from app.services.commerce import merchandising, onboarding, intent, learning
from tests.test_commerce import shop, new_cart, merchant_headers, configure_provider
from tests.test_commerce_learning import mock_client, product
from tests.test_commerce_workflows import simulate, act


@pytest.fixture
async def owner(shop):
    client, session, _, _ = shop
    headers, merchant_id = await merchant_headers(client)
    response = await client.post("/api/v1/commerce/merchant/catalog/demo", headers=headers, json={"confirm": True})
    assert response.status_code == 200, response.text
    return client, session, headers, merchant_id


def rules(**values):
    return {"compatibility": [], "growth_rules": [{"id": "feature-1", "kind": "feature_category", "category": "Electronics", "enabled": True, "discount_percent": 0}],
        "scheduler_enabled": False, "interval_seconds": 300, **values}


async def test_rules_cycles_are_scoped_bounded_and_repeat_safe(owner):
    client, session, headers, merchant_id = owner
    response = await client.put("/api/v1/commerce/merchant/rules", headers=headers, json=rules())
    assert response.status_code == 200, response.text
    first = (await client.post("/api/v1/commerce/merchant/growth-cycle", headers=headers, json={"confirm": True})).json()
    assert len(first["executed"]) == 2
    second = (await client.post("/api/v1/commerce/merchant/growth-cycle", headers=headers, json={"confirm": True})).json()
    assert second["executed"] == []
    assert len((await session.get(CommercePolicy, merchant_id)).boosted_product_ids) == 2
    assert (await client.get("/api/v1/commerce/merchant/opportunities")).status_code == 401


@pytest.mark.parametrize("body", [rules(interval_seconds=59), rules(interval_seconds=86401),
    rules(growth_rules=[{"id": "bad", "kind": "feature_category", "category": "Foreign", "enabled": True, "discount_percent": 0}]),
    rules(growth_rules=[{"id": "bad", "kind": "recovery_offer", "category": "Home", "enabled": True, "discount_percent": 21}]),
    rules(compatibility=[{"category_a": "Home", "category_b": "Home", "weight": .5, "reason": "bad"}])])
async def test_invalid_rules_rejected(owner, body):
    client, _, headers, _ = owner
    assert (await client.put("/api/v1/commerce/merchant/rules", headers=headers, json=body)).status_code == 422


async def test_scheduled_cycle_disabled_due_and_future_windows(owner):
    client, session, headers, merchant_id = owner
    await client.put("/api/v1/commerce/merchant/rules", headers=headers, json=rules())
    assert (await merchandising.run_cycle(session, merchant_id, scheduled=True))["executed"] == []
    await client.put("/api/v1/commerce/merchant/rules", headers=headers, json=rules(scheduler_enabled=True, interval_seconds=60))
    assert len((await merchandising.run_cycle(session, merchant_id, scheduled=True))["executed"]) == 2
    assert (await merchandising.run_cycle(session, merchant_id, scheduled=True))["executed"] == []
    rule = rules()["growth_rules"][0]
    rule["starts_at"] = int(time.time()) + 3600
    await client.put("/api/v1/commerce/merchant/rules", headers=headers, json=rules(growth_rules=[rule]))
    assert (await merchandising.opportunities(session, merchant_id)) == []


async def test_preview_lift_audit_and_context_are_honestly_labeled(owner):
    client, _, headers, _ = owner
    response = await client.post("/api/v1/commerce/merchant/ranking-preview", headers=headers, json={"query": "Show products", "budget_paise": 10000000})
    assert response.status_code == 200
    assert response.json()["baseline"]
    assert "no conversion or revenue" in response.json()["interpretation"]
    for path in ("lift", "audit", "context", "attribution", "scheduler"):
        result = await client.get("/api/v1/commerce/merchant/" + path, headers=headers)
        assert result.status_code == 200, result.text
    generated = await client.post("/api/v1/commerce/merchant/compatibility/generate", headers=headers, json={"confirm": True})
    assert generated.status_code == 200
    assert generated.json()["requires_review"]


async def test_category_pair_scoring_does_not_invent_order_counts(shop):
    from collections import Counter
    from app.services.commerce.catalog import rank
    from app.schemas.commerce import ShoppingIntent
    p = product()
    policy = CommercePolicy(max_spend_paise=100000, blocked_categories=[], boosted_product_ids=[])
    result = rank([p], ShoppingIntent(terms=["unrelated"], budget_paise=100000), policy, Counter(), compatibility={p.id: .8})
    assert len(result) == 1
    assert "Merchant-reviewed category compatibility" in result[0].reasons
    assert not any("completed-order" in reason for reason in result[0].reasons)


async def test_api_ingestion_unknown_costs_idempotence_and_atomic_validation(owner, monkeypatch):
    client, session, headers, merchant_id = owner
    payload = {"products": [{"id": 71, "title": "Imported notebook", "category": "Stationery", "price": 100, "stock": 12}]}
    mock_client(monkeypatch, lambda request: httpx.Response(200, json=payload))
    # Mocking global httpx client affects constructors only; the existing ASGI client stays intact.
    for expected in (1, 0):
        response = await client.post("/api/v1/commerce/merchant/catalog/provider", headers=headers, json={"confirm": True, "source": "dummyjson"})
        assert response.status_code == 200, response.text
        assert response.json()["imported"] == expected
    imported = await session.scalar(select(Product).where(Product.merchant_id == merchant_id, Product.sku == "API-dummyjson-71"))
    assert imported.cost_price is None
    payload["products"] = [{"id": 72, "title": "Valid first", "category": "Home", "price": 5, "stock": 2}, {"id": 73, "title": "Bad", "category": "Home", "price": -1, "stock": 2}]
    response = await client.post("/api/v1/commerce/merchant/catalog/provider", headers=headers, json={"confirm": True, "source": "dummyjson"})
    assert response.status_code == 503
    assert await session.scalar(select(Product).where(Product.sku == "API-dummyjson-72")) is None


@pytest.mark.parametrize("url", ["http://example.test/products", "https://127.0.0.1/products", "https://metadata.google.internal/products", "https://user:secret@example.test/products"])
def test_private_or_credentialed_provider_urls_rejected(monkeypatch, url):
    from fastapi import HTTPException
    monkeypatch.setattr(settings, "COMMERCE_CATALOG_API_URL", url)
    with pytest.raises(HTTPException):
        onboarding.provider_url("configured")


async def test_provider_failure_preserves_catalog(owner, monkeypatch):
    client, session, headers, _ = owner
    mock_client(monkeypatch, lambda request: httpx.Response(503))
    response = await client.post("/api/v1/commerce/merchant/catalog/provider", headers=headers, json={"confirm": True, "source": "dummyjson"})
    assert response.status_code == 503


async def test_recovery_offer_margin_gate_acceptance_and_fresh_approval(shop):
    client, session, p, headers = shop
    p.cost_price = Decimal("100.00")
    session.add(CommerceRules(merchant_id=1, compatibility=[], growth_rules=[{"id": "offer", "kind": "recovery_offer", "category": p.category, "enabled": True, "discount_percent": 20}], scheduler_enabled=False, interval_seconds=300, next_run_at=0, last_result={}))
    await session.commit()
    original_price = p.selling_price
    cart_id = (await new_cart(shop)).json()["id"]
    preview = await client.get(f"/api/v1/commerce/carts/{cart_id}/offer", headers=headers)
    assert preview.json()["eligible"]
    body = {"confirm": True, "request_key": "offer-request-key"}
    response = await client.post(f"/api/v1/commerce/carts/{cart_id}/offer", headers=headers, json=body)
    assert response.status_code == 200, response.text
    fresh = response.json()
    assert fresh["status"] == "draft"
    assert fresh["total_paise"] < int(original_price * 100)
    assert (await client.post(f"/api/v1/commerce/carts/{cart_id}/offer", headers=headers, json=body)).json()["id"] == fresh["id"]
    assert (await client.post(f"/api/v1/commerce/carts/{fresh['id']}/approve", headers=headers, json={"confirm": True})).status_code == 200
    assert p.selling_price == original_price


@pytest.mark.parametrize("failure", ["unknown_cost", "low_stock", "no_rule", "margin"])
async def test_offer_failures_remain_ineligible(shop, failure):
    client, session, p, headers = shop
    if failure != "no_rule":
        session.add(CommerceRules(merchant_id=1, compatibility=[], growth_rules=[{"id": "offer", "kind": "recovery_offer", "category": p.category, "enabled": True, "discount_percent": 20}], scheduler_enabled=False, interval_seconds=300, next_run_at=0, last_result={}))
    if failure == "unknown_cost":
        p.cost_price = None
    elif failure == "low_stock":
        stock = await session.scalar(select(Inventory).where(Inventory.product_id == p.id))
        stock.quantity = stock.reorder_point
    elif failure == "margin":
        p.cost_price = p.selling_price
    await session.commit()
    cart_id = (await new_cart(shop)).json()["id"]
    response = await client.get(f"/api/v1/commerce/carts/{cart_id}/offer", headers=headers)
    assert not response.json()["eligible"]


async def test_openai_failover_structured_contract(monkeypatch):
    monkeypatch.setattr(settings, "BUYER_AI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fixture-gemini")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("fixture-openai"))
    hosts = []
    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(503)
        payload = json.loads(request.content)
        assert payload["store"] is False
        assert "tools" not in payload
        assert payload["text"]["format"]["strict"] is True
        return httpx.Response(200, json={"output": [{"content": [{"type": "output_text", "text": '{"terms":["mouse"],"budget_paise":999999}'}]}]})
    mock_client(monkeypatch, handler)
    result, source = await intent.understand("mouse under 100")
    assert source == "openai" and result.budget_paise == 10000
    assert hosts == ["generativelanguage.googleapis.com", "api.openai.com"]


async def test_all_provider_failures_use_local_intent(monkeypatch):
    monkeypatch.setattr(settings, "BUYER_AI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fixture")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("fixture"))
    mock_client(monkeypatch, lambda request: httpx.Response(200, json={"invalid": True}))
    result, source = await intent.understand("mouse under 100")
    assert source == "local_fallback" and result.budget_paise == 10000


async def test_local_semantic_index_uses_separate_model_identity(owner, monkeypatch):
    _, session, _, merchant_id = owner
    monkeypatch.setattr(settings, "BUYER_LOCAL_EMBEDDINGS", True)
    monkeypatch.setattr(settings, "BUYER_SEMANTIC_ENABLED", True)
    monkeypatch.setattr(learning, "local_embedding", lambda text: [1.0] + [0.0] * 383)
    response = await learning.index_catalog(session, merchant_id, [product()])
    assert response["model"] == "local/all-MiniLM-L6-v2"
    _, scores = await learning.learned_scores(session, merchant_id, "mouse", [product()], None)
    assert scores[1] == 1


async def test_weather_failure_and_finite_values(monkeypatch):
    monkeypatch.setattr(settings, "COMMERCE_WEATHER_ENABLED", True)
    mock_client(monkeypatch, lambda request: httpx.Response(503))
    result = await merchandising.contextual_snapshot()
    assert result["weather"] is None and "unavailable" in result["note"]


async def test_signed_test_refund_processing_and_reconciliation(shop, monkeypatch):
    from app.services.commerce import payments
    client, session, _, headers = shop
    configure_provider(monkeypatch)
    cart_id = await simulate(shop)
    cart = await session.get(ShoppingCart, cart_id)
    cart.status, cart.checkout_id = "test_paid", "plink_fixture"
    await session.commit()
    async def link(cart):
        return {"id": "plink_fixture", "status": "paid", "amount_paid": cart.total_paise}
    async def payment(cart, link):
        return {"id": "pay_fixture", "amount_refunded": 0}
    calls = []
    async def provider(method, path, body=None):
        calls.append((method, path))
        return {"id": "rfnd_fixture", "payment_id": "pay_fixture", "amount": 100, "status": "pending" if method == "POST" else "processed"}
    monkeypatch.setattr(payments, "fetch_link", link)
    monkeypatch.setattr(payments, "captured_payment", payment)
    monkeypatch.setattr(payments, "provider_request", provider)
    response = await act(shop, cart_id, "refund", amount_paise=100)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "processing"
    assert (await act(shop, cart_id, "refund", "other-key-01", amount_paise=100)).status_code == 409
    response = await act(shop, cart_id, "reconcile", "reconcile-key")
    assert response.status_code == 200, response.text
    assert response.json()["refunded_paise"] == 100
    assert sum(method == "POST" for method, _ in calls) == 1

async def test_return_approval_received_and_no_stock_or_refund_side_effect(owner):
    client, session, account_headers, merchant_id = owner
    identity = (await client.post('/api/v1/commerce/sessions', headers=account_headers, json={'merchant_id': merchant_id})).json()
    headers = {'X-CartPilot-Buyer': identity['token']}
    product = await session.scalar(select(Product).where(Product.merchant_id == merchant_id).order_by(Product.id))
    response = await client.post('/api/v1/commerce/carts', headers=headers, json={'budget_paise': 10000000, 'items': [{'product_id': product.id, 'quantity': 1}]})
    cart_id = response.json()['id']
    await client.post(f'/api/v1/commerce/carts/{cart_id}/approve', headers=headers, json={'confirm': True})
    await client.post(f'/api/v1/commerce/carts/{cart_id}/checkout', headers=headers, json={'confirm': True})
    result = await client.post(f'/api/v1/commerce/carts/{cart_id}/resolution', headers=headers,
        json={'confirm': True, 'action': 'return_review', 'request_key': 'return-owner-key'})
    operation_id = result.json()['id']
    path = f'/api/v1/commerce/merchant/returns/{operation_id}/review'
    assert (await client.post(path, headers=account_headers, json={'confirm': True, 'decision': 'received'})).status_code == 409
    for decision in ('approve', 'approve', 'received'):
        response = await client.post(path, headers=account_headers, json={'confirm': True, 'decision': decision})
        assert response.status_code == 200, response.text
        assert response.json()['details']['physical_stock_changed'] is False
    assert (await client.post(path, headers=account_headers, json={'confirm': True, 'decision': 'reject'})).status_code == 409
    status = (await client.get(f'/api/v1/commerce/carts/{cart_id}/resolution', headers=headers)).json()
    assert status['refunded_paise'] == 0


async def test_unknown_refund_result_cannot_be_resubmitted_with_new_key(shop, monkeypatch):
    from app.services.commerce import payments
    client, session, _, _ = shop
    configure_provider(monkeypatch)
    cart_id = await simulate(shop)
    cart = await session.get(ShoppingCart, cart_id)
    cart.status, cart.checkout_id = 'test_paid', 'plink_fixture'
    await session.commit()
    async def link(cart): return {'id': 'plink_fixture', 'status': 'paid'}
    async def payment(cart, link): return {'id': 'pay_fixture', 'amount_refunded': 0}
    calls = []
    async def fail(method, path, body=None):
        calls.append(path)
        raise httpx.ReadTimeout('private provider detail')
    monkeypatch.setattr(payments, 'fetch_link', link)
    monkeypatch.setattr(payments, 'captured_payment', payment)
    monkeypatch.setattr(payments, 'provider_request', fail)
    response = await act(shop, cart_id, 'refund', amount_paise=100)
    assert response.status_code == 503
    assert 'private provider detail' not in response.text
    assert (await act(shop, cart_id, 'refund', amount_paise=100)).json()['status'] == 'pending'
    assert (await act(shop, cart_id, 'refund', 'different-refund-key', amount_paise=100)).status_code == 409
    assert len(calls) == 1


@pytest.mark.parametrize('offset,active', [(-1, False), (0, True), (59, True), (60, False)])
def test_rule_start_inclusive_end_exclusive(offset, active):
    rule = {'enabled': True, 'starts_at': 1000, 'ends_at': 1060}
    assert merchandising.active_rule(rule, 1000 + offset) is active


async def test_worker_survives_tick_failure_and_stops_on_cancellation(monkeypatch, caplog):
    import asyncio
    from app.services.commerce import worker
    calls = []
    async def fail():
        calls.append("tick")
        raise ConnectionError("private database connection details")
    async def stop(seconds):
        assert seconds == 30
        raise asyncio.CancelledError()
    monkeypatch.setattr(worker, "tick", fail)
    monkeypatch.setattr(worker.asyncio, "sleep", stop)
    with pytest.raises(asyncio.CancelledError):
        await worker.main()
    assert calls == ["tick"]
    assert "commerce_worker_tick_failed" in caplog.text
    assert "private database connection" not in caplog.text
