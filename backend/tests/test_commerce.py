"""Buyer happy paths, invalid/boundary inputs, isolation and provider failures."""
import hashlib
import hmac
import json
import time
from decimal import Decimal
import httpx
import pytest
from sqlalchemy import select, func
from app.main import app
from app.api.deps import get_database_session
from app.core.config import settings
from app.models.commerce import CommercePolicy, ShopperSession, ShoppingCart, CommerceEvent
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.services.commerce import ledger


@pytest.fixture
async def shop(seeded_session, async_client):
    async def override():
        yield seeded_session
    app.dependency_overrides[get_database_session] = override
    product = await seeded_session.scalar(select(Product).where(Product.merchant_id == 1, Product.status == "active").order_by(Product.id))
    stock = await seeded_session.scalar(select(Inventory).where(Inventory.product_id == product.id))
    stock.quantity = 100
    stock.reserved_quantity = 0
    stock.unavailable_quantity = 0
    seeded_session.add(CommercePolicy(merchant_id=1, published=True, max_spend_paise=10000000, blocked_categories=[], boosted_product_ids=[]))
    await seeded_session.commit()
    result = await async_client.post("/api/v1/commerce/sessions", json={"merchant_id": 1})
    assert result.status_code == 201
    headers = {"X-CartPilot-Buyer": result.json()["token"]}
    try:
        yield async_client, seeded_session, product, headers
    finally:
        app.dependency_overrides.clear()


async def new_cart(shop, **overrides):
    client, _, product, headers = shop
    body = {"budget_paise": 10000000, "items": [{"product_id": product.id, "quantity": 1}], **overrides}
    return await client.post("/api/v1/commerce/carts", headers=headers, json=body)


async def approved_cart(shop):
    client, _, _, headers = shop
    result = await new_cart(shop)
    assert result.status_code == 201, result.text
    cart_id = result.json()["id"]
    result = await client.post(f"/api/v1/commerce/carts/{cart_id}/approve", headers=headers, json={"confirm": True})
    assert result.status_code == 200, result.text
    return cart_id


async def test_storefront_projection_and_search(shop):
    client, _, product, headers = shop
    store = await client.get("/api/v1/commerce/storefront/1")
    assert store.status_code == 200
    public_product = next(p for p in store.json()["products"] if p["id"] == product.id)
    assert "cost_price" not in public_product
    assert "merchant_id" not in public_product
    response = await client.post("/api/v1/commerce/search", headers=headers, json={"query": product.name})
    assert response.status_code == 200
    assert any(p["id"] == product.id for p in response.json()["products"])
    assert response.json()["intent_source"] == "local"


async def test_full_simulation_is_approved_idempotent_and_not_a_sale(shop):
    client, session, _, headers = shop
    orders_before = await session.scalar(select(func.count()).select_from(Order))
    cart_id = await approved_cart(shop)
    for _ in range(2):
        response = await client.post(f"/api/v1/commerce/carts/{cart_id}/checkout", headers=headers, json={"confirm": True})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "simulated"
    audit = (await client.get(f"/api/v1/commerce/carts/{cart_id}/audit", headers=headers)).json()
    assert audit["valid"]
    assert [e["event"] for e in audit["events"]] == ["intent_mandate", "cart_proposed", "cart_mandate", "payment_simulated"]
    assert await session.scalar(select(func.count()).select_from(Order)) == orders_before


@pytest.mark.parametrize("body", [
    {"budget_paise": 0, "items": []},
    {"budget_paise": 100000001, "items": []},
    {"budget_paise": 10000, "items": [{"product_id": 1, "quantity": 0}]},
    {"budget_paise": 10000, "items": [{"product_id": 1, "quantity": 21}]},
    {"budget_paise": 10000, "items": [{"product_id": 1, "quantity": 1, "unit_price_paise": 1}]},
    {"budget_paise": 10000, "items": [{"product_id": 1, "quantity": 1}] * 2},
])
async def test_invalid_cart_input(shop, body):
    client, _, _, headers = shop
    assert (await client.post("/api/v1/commerce/carts", headers=headers, json=body)).status_code == 422


async def test_exact_budget_and_quantity_boundaries(shop):
    _, _, product, _ = shop
    price = int(product.selling_price * 100)
    assert (await new_cart(shop, budget_paise=price)).status_code == 201
    assert (await new_cart(shop, budget_paise=price - 1)).status_code == 422
    assert (await new_cart(shop, items=[{"product_id": product.id, "quantity": 20}])).status_code == 201


async def test_private_store_and_session_expiry(shop):
    client, session, _, headers = shop
    policy = await session.get(CommercePolicy, 1)
    policy.published = False
    await session.commit()
    assert (await client.get("/api/v1/commerce/storefront/1")).status_code == 401
    assert (await client.post("/api/v1/commerce/sessions", json={"merchant_id": 1})).status_code == 401
    identity = await session.get(ShopperSession, hashlib.sha256(headers["X-CartPilot-Buyer"].encode()).hexdigest())
    identity.expires_at = int(time.time()) - 1
    await session.commit()
    assert (await client.post("/api/v1/commerce/search", headers=headers, json={"query": "mouse"})).status_code == 401


async def test_capability_does_not_access_other_shopper_cart_or_merchant_controls(shop):
    client, _, _, headers = shop
    cart_id = (await new_cart(shop)).json()["id"]
    other = (await client.post("/api/v1/commerce/sessions", json={"merchant_id": 1})).json()
    other_headers = {"X-CartPilot-Buyer": other["token"]}
    for suffix in ("", "/audit"):
        assert (await client.get(f"/api/v1/commerce/carts/{cart_id}{suffix}", headers=other_headers)).status_code == 404
    assert (await client.get("/api/v1/commerce/policy", headers=headers)).status_code == 401
    assert (await client.get("/api/v1/commerce/growth", headers=headers)).status_code == 401


@pytest.mark.parametrize("change", ["price", "stock", "expired", "category", "tampered"])
async def test_fresh_validation_blocks_changed_cart(shop, change):
    client, session, product, headers = shop
    cart_id = (await new_cart(shop)).json()["id"]
    if change == "price":
        product.selling_price += Decimal("1.00")
    elif change == "stock":
        stock = await session.scalar(select(Inventory).where(Inventory.product_id == product.id))
        stock.quantity = 0
    elif change == "expired":
        (await session.get(ShoppingCart, cart_id)).expires_at = int(time.time())
    elif change == "category":
        (await session.get(CommercePolicy, 1)).blocked_categories = [product.category.casefold()]
    else:
        event = await session.scalar(select(CommerceEvent).where(CommerceEvent.cart_id == cart_id).order_by(CommerceEvent.sequence))
        event.payload = {"budget_paise": 1}
    await session.commit()
    result = await client.post(f"/api/v1/commerce/carts/{cart_id}/approve", headers=headers, json={"confirm": True})
    assert result.status_code in {409, 422}


async def test_checkout_requires_separate_approval_and_true_confirmation(shop):
    client, _, _, headers = shop
    cart_id = (await new_cart(shop)).json()["id"]
    assert (await client.post(f"/api/v1/commerce/carts/{cart_id}/checkout", headers=headers, json={"confirm": True})).status_code == 409
    assert (await client.post(f"/api/v1/commerce/carts/{cart_id}/approve", headers=headers, json={"confirm": False})).status_code == 422


async def test_unconfigured_razorpay_does_not_claim_cart(shop, monkeypatch):
    client, session, _, headers = shop
    monkeypatch.setattr(settings, "BUYER_RAZORPAY_TEST_ENABLED", False)
    cart_id = await approved_cart(shop)
    assert (await client.post(f"/api/v1/commerce/carts/{cart_id}/checkout", headers=headers, json={"confirm": True, "mode": "razorpay_test"})).status_code == 503
    assert (await session.get(ShoppingCart, cart_id)).status == "approved"


def configure_provider(monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(settings, "BUYER_RAZORPAY_TEST_ENABLED", True)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_fixture")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", SecretStr("fixture-not-a-real-secret"))
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SecretStr("fixture-webhook-secret"))


async def test_ambiguous_provider_failure_is_not_retried(shop, monkeypatch):
    client, session, _, headers = shop
    configure_provider(monkeypatch)
    calls = []
    async def fail(cart):
        calls.append(cart.id)
        raise httpx.ConnectError("private upstream detail")
    monkeypatch.setattr("app.services.commerce.payments.create_test_link", fail)
    cart_id = await approved_cart(shop)
    response = await client.post(f"/api/v1/commerce/carts/{cart_id}/checkout", headers=headers, json={"confirm": True, "mode": "razorpay_test"})
    assert response.status_code == 503
    assert "private upstream" not in response.text
    assert (await session.get(ShoppingCart, cart_id)).status == "checkout_pending"
    assert (await client.post(f"/api/v1/commerce/carts/{cart_id}/checkout", headers=headers, json={"confirm": True, "mode": "razorpay_test"})).status_code == 409
    assert calls == [cart_id]


async def test_test_provider_and_signed_idempotent_webhook(shop, monkeypatch):
    client, session, _, headers = shop
    configure_provider(monkeypatch)
    async def link(cart):
        return "plink_fixture", "https://rzp.io/i/fixture"
    monkeypatch.setattr("app.services.commerce.payments.create_test_link", link)
    cart_id = await approved_cart(shop)
    result = await client.post(f"/api/v1/commerce/carts/{cart_id}/checkout", headers=headers, json={"confirm": True, "mode": "razorpay_test"})
    assert result.status_code == 200, result.text
    cart = result.json()
    assert cart["status"] == "checkout_ready"
    entity = {"id": "plink_fixture", "reference_id": cart_id, "currency": "INR", "amount": cart["total_paise"], "amount_paid": cart["total_paise"], "status": "paid"}
    raw = json.dumps({"event": "payment_link.paid", "payload": {"payment_link": {"entity": entity}}}).encode()
    signature = hmac.new(b"fixture-webhook-secret", raw, hashlib.sha256).hexdigest()
    assert (await client.post("/api/v1/commerce/webhooks/razorpay", content=raw)).status_code == 401
    for _ in range(2):
        assert (await client.post("/api/v1/commerce/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": signature})).status_code == 200
    assert (await session.get(ShoppingCart, cart_id)).status == "test_paid"
    audit = (await client.get(f"/api/v1/commerce/carts/{cart_id}/audit", headers=headers)).json()
    assert audit["valid"]
    assert len([e for e in audit["events"] if e["event"] == "test_payment_verified"]) == 1


async def test_cross_merchant_product_rejected(shop):
    _, session, _, _ = shop
    foreign = await session.scalar(select(Product).where(Product.merchant_id != 1))
    if foreign:
        assert (await new_cart(shop, items=[{"product_id": foreign.id, "quantity": 1}])).status_code == 422
    else:
        assert (await new_cart(shop, items=[{"product_id": 999999, "quantity": 1}])).status_code == 422


def test_ledger_canonical_hash_is_payload_sensitive():
    args = ("cart", 1, "intent", {"a": 1}, 100, ledger.GENESIS)
    assert ledger.digest(*args) == ledger.digest(*args)
    assert ledger.digest(*args) != ledger.digest("cart", 1, "intent", {"a": 2}, 100, ledger.GENESIS)

async def merchant_headers(client):
    response = await client.post('/api/v1/auth/signup', json={
        'name': 'Commerce Owner', 'store_name': 'New Commerce Store',
        'email': 'commerce-owner@example.test', 'password': 'fixture-long-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}, response.json()['user']['merchant_id']


async def test_merchant_policies_are_scoped_and_default_private(shop):
    client, _, product, _ = shop
    headers, merchant = await merchant_headers(client)
    result = await client.get('/api/v1/commerce/policy', headers=headers)
    assert result.status_code == 200
    assert not result.json()['published']
    policy = {'published': True, 'max_spend_paise': 10000, 'blocked_categories': [' Books ', 'books'], 'boosted_product_ids': []}
    result = await client.put('/api/v1/commerce/policy', headers=headers, json=policy)
    assert result.status_code == 200
    assert result.json()['blocked_categories'] == ['books']
    assert (await client.get(f'/api/v1/commerce/storefront/{merchant}')).status_code == 200
    policy['boosted_product_ids'] = [product.id]
    assert (await client.put('/api/v1/commerce/policy', headers=headers, json=policy)).status_code == 422
    policy['max_spend_paise'] = 0
    assert (await client.put('/api/v1/commerce/policy', headers=headers, json=policy)).status_code == 422
    growth = await client.get('/api/v1/commerce/growth', headers=headers)
    assert growth.status_code == 200
    assert growth.json()['counts'] == {}
    assert growth.json()['real_revenue_paise'] == 0


async def test_catalog_and_model_endpoints_require_owner_identity(shop):
    client, _, _, shopper_headers = shop
    assert (await client.post('/api/v1/commerce/catalog/import', headers=shopper_headers, json={'csv_text': 'bad'})).status_code == 401
    headers, _ = await merchant_headers(client)
    result = await client.post('/api/v1/commerce/models/train', headers=headers, json={'confirm': True})
    assert result.status_code == 422
    assert '30' in result.json()['detail']
    assert (await client.post('/api/v1/commerce/models/index', headers=headers, json={'confirm': True})).status_code == 503
    template = await client.get('/api/v1/commerce/catalog/template', headers=headers)
    assert template.status_code == 200
    result = await client.post('/api/v1/commerce/catalog/import', headers=headers, json={'csv_text': template.text})
    assert result.status_code == 201
    assert result.json()['imported'] == 1


async def test_price_change_after_approval_blocks_checkout(shop):
    client, session, product, headers = shop
    cart_id = await approved_cart(shop)
    product.selling_price += Decimal('1.00')
    await session.commit()
    result = await client.post(f'/api/v1/commerce/carts/{cart_id}/checkout', headers=headers, json={'confirm': True})
    assert result.status_code == 409
    assert (await session.get(ShoppingCart, cart_id)).status == 'approved'


async def test_public_budget_enforced_and_commerce_is_not_cacheable(shop):
    client, session, _, headers = shop
    from app.services.auth_limits import record_attempt
    response = await client.get('/api/v1/commerce/storefront/1')
    assert response.headers['cache-control'] == 'no-store'
    key = hashlib.sha256(b'commerce-peer:127.0.0.1').hexdigest()
    for _ in range(181):
        await record_attempt(session, key, 180, int(time.time()), 60)
    await session.commit()
    response = await client.post('/api/v1/commerce/search', headers=headers, json={'query': 'mouse'})
    assert response.status_code == 429
    assert int(response.headers['retry-after']) > 0


async def test_default_search_lists_in_stock_catalog(shop):
    client, _, product, headers = shop
    response = await client.post('/api/v1/commerce/search', headers=headers, json={'query': 'Show products'})
    assert response.status_code == 200
    assert 0 < len(response.json()['products']) <= 24
    assert all(p['available'] > 0 for p in response.json()['products'])
