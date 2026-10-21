"""Password-proven email recovery preserves account ownership and sessions."""
from sqlalchemy import select

from app.models.account import Account
from app.models.merchant import Merchant
from tests.test_accounts_management import account_client, signup


async def test_recovery_updates_both_emails_and_revokes_sessions(account_client):
    client, session = account_client
    old_headers, data = await signup(client)
    response = await client.post("/api/v1/auth/recover-email", json={
        "store_name": " store ", "password": "correct horse battery staple", "new_email": " New@Example.test ",
    })
    assert response.status_code == 200 and response.json()["email_changed"]
    assert (await client.get("/api/v1/auth/me", headers=old_headers)).status_code == 401
    account = await session.scalar(select(Account))
    merchant = await session.get(Merchant, data["user"]["merchant_id"])
    assert account.email == merchant.email == "new@example.test"
    assert (await client.post("/api/v1/auth/login", json={"email": "new@example.test", "password": "correct horse battery staple"})).status_code == 200


async def test_failed_recovery_preserves_identity_and_session(account_client):
    client, session = account_client
    headers, _ = await signup(client)
    response = await client.post("/api/v1/auth/recover-email", json={
        "store_name": "Store", "password": "incorrect long password", "new_email": "other@example.test",
    })
    assert response.status_code == 401
    assert (await session.scalar(select(Account))).email == "owner@example.test"
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200


async def test_duplicate_email_rolls_back_recovery(account_client):
    client, _ = account_client
    headers, _ = await signup(client)
    # Give the other store a distinct password so store-name matching is unambiguous.
    await client.post("/api/v1/auth/signup", json={"email": "other@example.test", "name": "Other", "store_name": "Other store", "password": "another correct password"})
    response = await client.post("/api/v1/auth/recover-email", json={
        "store_name": "Store", "password": "correct horse battery staple", "new_email": "other@example.test",
    })
    assert response.status_code == 409
    current = await client.get("/api/v1/auth/me", headers=headers)
    assert current.status_code == 200 and current.json()["email"] == "owner@example.test"


async def test_ambiguous_store_is_rejected(account_client):
    client, _ = account_client
    await signup(client)
    await signup(client, "second@example.test")
    response = await client.post("/api/v1/auth/recover-email", json={
        "store_name": "Store", "password": "correct horse battery staple", "new_email": "new@example.test",
    })
    assert response.status_code == 401


async def test_recovery_validation_and_same_email_boundary(account_client):
    client, _ = account_client
    await signup(client)
    body = {"store_name": "Store", "password": "correct horse battery staple", "new_email": "owner@example.test"}
    assert (await client.post("/api/v1/auth/recover-email", json=body)).status_code == 409
    for patch in [{"store_name": " "}, {"new_email": "invalid"}, {"password": "short"}, {"extra": True}]:
        assert (await client.post("/api/v1/auth/recover-email", json={**body, **patch})).status_code == 422
