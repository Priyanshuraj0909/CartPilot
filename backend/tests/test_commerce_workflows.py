"""Durable shopper workflows, explicit financial confirmation and ownership boundaries."""
import time
import pytest
from sqlalchemy import select
from app.models.commerce import ShoppingCart, CommerceEvent
from app.models.commerce_workflows import CommerceOperation
from tests.test_commerce import shop, new_cart, approved_cart


async def simulate(shop):
    client, _, _, headers = shop
    cart_id = await approved_cart(shop)
    response = await client.post(f"/api/v1/commerce/carts/{cart_id}/checkout", headers=headers, json={"confirm": True})
    assert response.status_code == 200
    return cart_id


async def act(shop, cart_id, action, key="request-key-001", **values):
    client, _, _, headers = shop
    return await client.post(f"/api/v1/commerce/carts/{cart_id}/resolution", headers=headers,
        json={"action": action, "request_key": key, "confirm": True, **values})


async def test_simulated_partial_full_refunds_and_idempotency(shop):
    client, _, product, headers = shop
    cart_id = await simulate(shop)
    total = int(product.selling_price * 100)
    first = await act(shop, cart_id, "refund", amount_paise=1)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "succeeded"
    duplicate = await act(shop, cart_id, "refund", amount_paise=1)
    assert duplicate.json()["id"] == first.json()["id"]
    assert (await act(shop, cart_id, "refund", "different-key", amount_paise=total)).status_code == 422
    result = await act(shop, cart_id, "refund", "remaining-key", amount_paise=total - 1)
    assert result.status_code == 200, result.text
    cart = (await client.get(f"/api/v1/commerce/carts/{cart_id}", headers=headers)).json()
    assert cart["status"] == "simulated_refunded"
    assert (await act(shop, cart_id, "refund", "excess-key-01", amount_paise=1)).status_code == 409


async def test_cancel_then_recover_requires_fresh_approval(shop):
    client, _, _, headers = shop
    cart_id = await approved_cart(shop)
    assert (await act(shop, cart_id, "cancel")).status_code == 200
    recovered = await act(shop, cart_id, "recover", "recovery-key")
    assert recovered.status_code == 200, recovered.text
    new_id = recovered.json()["details"]["recovered_cart_id"]
    fresh = (await client.get(f"/api/v1/commerce/carts/{new_id}", headers=headers)).json()
    assert fresh["status"] == "draft"
    assert (await client.post(f"/api/v1/commerce/carts/{new_id}/checkout", headers=headers, json={"confirm": True})).status_code == 409


async def test_resolution_invalid_input_and_unpaid_refund(shop):
    client, _, _, headers = shop
    cart_id = (await new_cart(shop)).json()["id"]
    assert (await act(shop, cart_id, "refund", amount_paise=1)).status_code == 409
    for body in ({"action": "refund", "request_key": "request-key", "confirm": False},
                 {"action": "refund", "request_key": "request-key", "confirm": True, "amount_paise": 0}):
        assert (await client.post(f"/api/v1/commerce/carts/{cart_id}/resolution", headers=headers, json=body)).status_code == 422


async def test_revision_preserves_original_and_resets_approval(shop):
    client, _, product, headers = shop
    cart_id = await approved_cart(shop)
    revised = await client.post(f"/api/v1/commerce/carts/{cart_id}/revise", headers=headers,
        json={"budget_paise": 10000000, "items": [{"product_id": product.id, "quantity": 2}]})
    assert revised.status_code == 200
    assert revised.json()["id"] != cart_id
    assert revised.json()["status"] == "draft"
    assert revised.json()["total_paise"] == 2 * int(product.selling_price * 100)
    assert (await client.get(f"/api/v1/commerce/carts/{cart_id}", headers=headers)).json()["status"] == "approved"


async def test_cart_handoff_is_single_use_and_scoped(shop):
    client, _, _, headers = shop
    cart_id = await approved_cart(shop)
    result = await client.post(f"/api/v1/commerce/carts/{cart_id}/handoff", headers=headers, json={"confirm": True})
    token = result.json()["path"].split("handoff=")[1]
    new_identity = (await client.post("/api/v1/commerce/sessions", json={"merchant_id": 1})).json()
    new_headers = {"X-CartPilot-Buyer": new_identity["token"]}
    response = await client.post("/api/v1/commerce/handoff/redeem", headers=new_headers, json={"token": token})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "draft"
    assert (await client.get(f"/api/v1/commerce/carts/{cart_id}", headers=headers)).status_code == 404
    assert (await client.post("/api/v1/commerce/handoff/redeem", headers=new_headers, json={"token": token})).status_code == 404


async def test_chat_saved_context_and_no_implicit_financial_action(shop):
    client, session, product, headers = shop
    result = await client.post("/api/v1/commerce/chat", headers=headers, json={"message": product.name, "budget_paise": 10000000})
    assert result.status_code == 200, result.text
    assert result.json()["products"]
    history = (await client.get("/api/v1/commerce/conversation", headers=headers)).json()
    assert len(history["messages"]) == 2
    cart_id = await simulate(shop)
    result = await client.post("/api/v1/commerce/chat", headers=headers, json={"message": "refund this order now", "cart_id": cart_id})
    assert result.status_code == 200
    assert "refund" in result.json()["actions"]
    assert (await session.scalars(select(CommerceOperation))).all() == []
    assert (await client.delete("/api/v1/commerce/conversation", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/commerce/conversation", headers=headers)).json()["messages"] == []


async def test_chat_add_builds_only_draft_and_bounds_quantities(shop):
    client, _, product, headers = shop
    result = await client.post("/api/v1/commerce/chat", headers=headers,
        json={"message": "add " + product.name, "budget_paise": 10000000})
    assert result.status_code == 200, result.text
    assert result.json()["cart"]["status"] == "draft"
    assert (await client.post("/api/v1/commerce/chat", headers=headers,
        json={"message": "add 99 " + product.name, "budget_paise": 10000000})).status_code == 422


async def test_tampered_audit_blocks_resolution(shop):
    client, session, _, headers = shop
    cart_id = await simulate(shop)
    row = await session.scalar(select(CommerceEvent).where(CommerceEvent.cart_id == cart_id))
    row.payload = {"tampered": True}
    await session.commit()
    assert (await act(shop, cart_id, "refund", amount_paise=1)).status_code == 409


async def test_pending_operation_prevents_duplicate_refund(shop):
    _, session, _, _ = shop
    cart_id = await simulate(shop)
    session.add(CommerceOperation(id="pending", cart_id=cart_id, request_key="original-key", kind="refund", status="pending", amount_paise=1, details={}, created_at=int(time.time())))
    await session.commit()
    assert (await act(shop, cart_id, "refund", amount_paise=1)).status_code == 409

async def test_other_handoff_tokens_expire_when_ownership_changes(shop):
    client, _, _, headers = shop
    cart_id = (await new_cart(shop)).json()['id']
    tokens = []
    for _ in range(2):
        result = await client.post(f'/api/v1/commerce/carts/{cart_id}/handoff', headers=headers, json={'confirm': True})
        tokens.append(result.json()['path'].split('handoff=')[1])
    new_identity = (await client.post('/api/v1/commerce/sessions', json={'merchant_id': 1})).json()
    next_headers = {'X-CartPilot-Buyer': new_identity['token']}
    assert (await client.post('/api/v1/commerce/handoff/redeem', headers=next_headers, json={'token': tokens[0]})).status_code == 200
    assert (await client.post('/api/v1/commerce/handoff/redeem', headers=next_headers, json={'token': tokens[1]})).status_code == 404

@pytest.mark.parametrize('query,expected', [('add 2 mouse and 1 keyboard', {1: 2, 2: 1}), ('add mouse', {1: 1}), ('replace with keyboard', {2: 1})])
def test_multi_product_draft_lines(query, expected):
    from app.services.commerce.conversation import draft_lines
    products = [{'id': 1, 'name': 'Wireless Mouse'}, {'id': 2, 'name': 'Keyboard'}]
    result = draft_lines(query, products, [])
    assert {row['product_id']: row['quantity'] for row in result} == expected


def test_unknown_chat_item_does_not_guess_a_product():
    from fastapi import HTTPException
    from app.services.commerce.conversation import draft_lines
    with pytest.raises(HTTPException):
        draft_lines('add a unicorn', [{'id': 1, 'name': 'Mouse'}], [])


async def test_return_review_has_no_automatic_refund(shop):
    client, session, _, headers = shop
    cart_id = await simulate(shop)
    response = await act(shop, cart_id, 'return_review', 'return-review-key')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'review_required'
    assert response.json()['details']['automatic_refund'] is False
    assert (await act(shop, cart_id, 'return_review', 'duplicate-return-key')).status_code == 409
    assert (await client.post(f"/api/v1/commerce/merchant/returns/{response.json()['id']}/review", json={'confirm': True, 'decision': 'approve'})).status_code == 401
