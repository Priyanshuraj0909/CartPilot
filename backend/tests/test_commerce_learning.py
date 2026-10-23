"""Ranking, AI fallback, learning boundaries, semantic freshness and atomic ingestion."""
from collections import Counter
import math
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.core.config import settings
from app.models.commerce import CommerceModel, CommercePolicy
from app.models.product import Product
from app.schemas.commerce import ShoppingIntent, StoreProduct
from app.services.commerce.catalog import local_intent, rank
from app.services.commerce import intent, learning
from app.services.commerce.ingestion import ingest, parse_csv


def product(id=1, **overrides):
    return StoreProduct(id=id, **{"name": "Wireless Mouse", "description": "Quiet everyday computer mouse", "category": "Electronics", "price_paise": 10000, "available": 5, **overrides})


def policy(**overrides):
    return CommercePolicy(merchant_id=1, **{"published": False, "max_spend_paise": 100000, "blocked_categories": [], "boosted_product_ids": [], **overrides})


def test_local_budget_and_query_boundaries():
    assert local_intent("mouse under ₹1,000.50").budget_paise == 100050
    assert local_intent("mouse").budget_paise is None
    assert local_intent("mouse under 0").budget_paise is None
    assert local_intent("mouse below 1000001").budget_paise is None


def test_rank_hard_filters_override_models_and_boosts():
    products = [product(), product(2, available=0), product(3, price_paise=100001), product(4, category="Restricted")]
    result = rank(products, ShoppingIntent(terms=["mouse"], budget_paise=100000), policy(blocked_categories=["restricted"], boosted_product_ids=[2, 3, 4]), Counter({2: 100, 3: 100}), behavioral={2: 1, 3: 1}, semantic={4: 1})
    assert [p.id for p in result] == [1]


def test_rank_semantic_match_and_transparent_boost():
    products = [product(1, name="Journal", description="Paper pages", category="Books"), product(2)]
    result = rank(products, ShoppingIntent(terms=["notebook"], budget_paise=100000), policy(boosted_product_ids=[1]), Counter(), semantic={1: .9})
    assert result[0].id == 1
    assert any("Semantic" in reason for reason in result[0].reasons)
    assert any("boost" in reason for reason in result[0].reasons)


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))


async def test_gemini_intent_structured_success_and_budget_override(monkeypatch):
    monkeypatch.setattr(settings, "BUYER_AI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fixture-key")
    def handler(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "fixture-key"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"terms":["mouse"],"budget_paise":999999}'}]}}]})
    mock_client(monkeypatch, handler)
    result, source = await intent.understand("mouse under 100")
    assert source == "gemini"
    assert result.budget_paise == 10000


@pytest.mark.parametrize("response", [httpx.Response(503), httpx.Response(200, json={}), httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"terms":["mouse"],"place_order":true}'}]}}]})])
async def test_gemini_failures_fall_back_without_actions(monkeypatch, response):
    monkeypatch.setattr(settings, "BUYER_AI_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fixture-key")
    mock_client(monkeypatch, lambda request: response)
    result, source = await intent.understand("mouse under 100")
    assert source == "local_fallback"
    assert result.budget_paise == 10000


def test_training_minimum_determinism_and_finite_vectors():
    with pytest.raises(ValueError):
        learning.train([[1, 2]] * 29)
    with pytest.raises(ValueError):
        learning.train([[1]] * 100)
    result = learning.train([[1, 2], [1, 3]] * 15)
    assert result == learning.train([[1, 2], [1, 3]] * 15)
    assert result["orders"] == 30
    assert result["dimensions"] == 16
    assert all(math.isfinite(x) for vector in result["vectors"].values() for x in vector)
    assert learning.cosine([1, 0], [1, 0]) == 1
    assert learning.cosine([], []) == 0


async def test_semantic_index_reuses_fresh_vectors_and_rejects_changed_text(seeded_session, monkeypatch):
    monkeypatch.setattr(settings, "BUYER_SEMANTIC_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fixture-key")
    calls = []
    async def embed(text, task):
        calls.append(task)
        return [1.0] + [0.0] * 767
    monkeypatch.setattr(learning, "embed", embed)
    products = [product()]
    assert (await learning.index_catalog(seeded_session, 1, products))["indexed"] == 1
    assert (await learning.index_catalog(seeded_session, 1, products))["indexed"] == 0
    _, scores = await learning.learned_scores(seeded_session, 1, "computer", products, None)
    assert scores[1] == 1
    _, changed = await learning.learned_scores(seeded_session, 1, "computer", [product(name="Changed")], None)
    assert changed == {}
    assert calls.count("RETRIEVAL_DOCUMENT") == 1


async def test_failed_semantic_index_retains_previous_model(seeded_session, monkeypatch):
    monkeypatch.setattr(settings, "BUYER_SEMANTIC_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fixture-key")
    data = {"model": settings.BUYER_EMBEDDING_MODEL, "vectors": {}, "fingerprints": {}}
    await learning.save_model(seeded_session, 1, "semantic", data)
    async def fail(*args):
        raise httpx.ConnectError("provider detail")
    monkeypatch.setattr(learning, "embed", fail)
    with pytest.raises(HTTPException) as caught:
        await learning.index_catalog(seeded_session, 1, [product()])
    assert caught.value.status_code == 503
    assert (await seeded_session.get(CommerceModel, (1, "semantic"))).data == data


async def test_embedding_provider_validates_dimensions(monkeypatch):
    monkeypatch.setattr(settings, "BUYER_SEMANTIC_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fixture-key")
    mock_client(monkeypatch, lambda request: httpx.Response(200, json={"embedding": {"values": [1.0]}}))
    with pytest.raises(ValueError):
        await learning.embed("test", "RETRIEVAL_QUERY")


HEADER = "sku,name,category,description,cost_price,selling_price,quantity\n"


async def test_catalog_atomic_import_and_existing_sku_protection(seeded_session):
    text = HEADER + 'NEW-001,Notebook,Books,"Plain, paper notebook",50,100,25\n'
    assert await ingest(seeded_session, 1, text) == {"imported": 1}
    with pytest.raises(HTTPException) as caught:
        await ingest(seeded_session, 1, text)
    assert caught.value.status_code == 409
    assert await seeded_session.scalar(select(func.count()).select_from(Product).where(Product.sku == "NEW-001")) == 1


@pytest.mark.parametrize("text", ["", HEADER, "sku,name\na,b\n", HEADER + "X,Name,Cat,Text,100,50,1\n", HEADER + "X,Name,Cat,Text,0,50,-1\n", HEADER + "X,Name,Cat,Text,0,50,1\n" * 2])
def test_catalog_rejects_invalid_rows(text):
    with pytest.raises(HTTPException) as caught:
        parse_csv(text)
    assert caught.value.status_code == 422


async def test_invalid_later_catalog_row_does_not_write_earlier_row(seeded_session):
    with pytest.raises(HTTPException):
        await ingest(seeded_session, 1, HEADER + "ATOMIC-1,Name,Cat,Text,0,50,1\nBROKEN\n")
    assert await seeded_session.scalar(select(Product).where(Product.sku == "ATOMIC-1")) is None

async def test_razorpay_http_contract_checks_amount_and_redirect(monkeypatch):
    import json
    import time
    from pydantic import SecretStr
    from app.models.commerce import ShoppingCart
    from app.services.commerce import payments
    monkeypatch.setattr(settings, 'BUYER_RAZORPAY_TEST_ENABLED', True)
    monkeypatch.setattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_fixture')
    monkeypatch.setattr(settings, 'RAZORPAY_KEY_SECRET', SecretStr('fixture-key'))
    cart = ShoppingCart(id='cart-fixture', total_paise=10000, expires_at=int(time.time()) + 1200)
    def handler(request):
        assert request.url.host == 'api.razorpay.com'
        body = json.loads(request.content)
        assert body['amount'] == 10000
        assert body['expire_by'] >= time.time() + 900
        assert body['notify'] == {'sms': False, 'email': False}
        return httpx.Response(200, json={'id': 'plink_fixture', 'short_url': 'https://rzp.io/i/fixture', 'amount': 10000, 'currency': 'INR'})
    mock_client(monkeypatch, handler)
    assert await payments.create_test_link(cart) == ('plink_fixture', 'https://rzp.io/i/fixture')


async def test_live_razorpay_keys_rejected(monkeypatch):
    from pydantic import SecretStr
    from app.services.commerce import payments
    monkeypatch.setattr(settings, 'BUYER_RAZORPAY_TEST_ENABLED', True)
    monkeypatch.setattr(settings, 'RAZORPAY_KEY_ID', 'rzp_live_fixture')
    monkeypatch.setattr(settings, 'RAZORPAY_KEY_SECRET', SecretStr('fixture-key'))
    with pytest.raises(HTTPException):
        payments.require_test_provider()
