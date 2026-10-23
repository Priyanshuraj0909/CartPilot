"""Deterministic, serialized cancellation/recovery/refund operations over test checkouts."""
import time
from uuid import uuid4
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.commerce import ShoppingCart, ShopperSession
from app.models.commerce_workflows import CommerceOperation
from app.schemas.commerce import CartRequest
from app.schemas.commerce_workflows import ResolutionRequest
from app.services.commerce import carts, ledger, payments


def projection(operation: CommerceOperation) -> dict:
    return {"id": operation.id, "action": operation.kind, "status": operation.status,
        "amount_paise": operation.amount_paise, "provider_id": operation.provider_id, "details": operation.details}


async def history(session: AsyncSession, cart_id: str) -> list[CommerceOperation]:
    return list((await session.scalars(select(CommerceOperation).where(CommerceOperation.cart_id == cart_id)
        .order_by(CommerceOperation.created_at, CommerceOperation.id))).all())


async def eligibility(session: AsyncSession, cart: ShoppingCart) -> dict:
    operations = await history(session, cart.id)
    refunded = sum(row.amount_paise for row in operations if row.kind == "refund" and row.status == "succeeded")
    pending = any(row.status in {"pending", "processing"} for row in operations)
    paid = cart.status in {"simulated", "test_paid"}
    return {"cart_id": cart.id, "status": cart.status, "refunded_paise": refunded,
        "refundable_paise": max(0, cart.total_paise - refunded) if paid else 0,
        "pending_operation": pending, "can_refund": paid and not pending and refunded < cart.total_paise,
        "can_cancel": not pending and cart.status in {"draft", "approved", "checkout_ready", "simulated_refunded", "test_refunded"},
        "can_recover": not pending and cart.status in {"draft", "approved", "checkout_ready", "cancelled"},
        "can_return_review": paid and not any(row.kind == "return_review" and row.status in {"review_required", "approved", "received"} for row in operations),
        "fulfillment": "not_fulfilled_test_checkout", "operations": [projection(row) for row in operations]}


async def reconcile(session: AsyncSession, cart: ShoppingCart) -> dict:
    if not cart.checkout_id and cart.status != "checkout_pending":
        return await eligibility(session, cart)
    try:
        link = await payments.fetch_link(cart)
        cart.checkout_id = link["id"]
        if link.get("status") == "paid":
            await payments.captured_payment(cart, link)
            if cart.status in {"checkout_pending", "checkout_ready"}:
                cart.status = "test_paid"
                await ledger.append(session, cart, "test_payment_reconciled", {"provider_id": link["id"], "amount_paise": cart.total_paise})
        elif link.get("status") in {"cancelled", "expired"} and cart.status in {"checkout_pending", "checkout_ready"}:
            cart.status = "cancelled"
            await ledger.append(session, cart, "checkout_closed", {"provider_status": link["status"]})
        elif link.get("status") == "created" and cart.status == "checkout_pending":
            url = link.get("short_url", "")
            from urllib.parse import urlparse
            if urlparse(url).scheme != "https" or urlparse(url).hostname != "rzp.io":
                raise ValueError("Invalid provider link")
            cart.checkout_url, cart.status = url, "checkout_ready"
            await ledger.append(session, cart, "checkout_reconciled", {"provider_id": link["id"]})
        for row in await history(session, cart.id):
            if row.kind == "refund" and row.status in {"pending", "processing"}:
                if row.provider_id:
                    refund = await payments.provider_request("GET", f"refunds/{row.provider_id}")
                else:
                    collection = await payments.provider_request("GET", f"payments/{row.details['payment_id']}/refunds")
                    matches = [item for item in collection.get("items", [])[:100] if item.get("notes", {}).get("operation_id") == row.id]
                    if len(matches) != 1:
                        continue
                    refund = matches[0]
                if refund.get("payment_id") != row.details["payment_id"] or refund.get("amount") != row.amount_paise:
                    raise ValueError("Refund does not match operation")
                row.provider_id = refund["id"]
                row.status = {"processed": "succeeded", "failed": "failed"}.get(refund.get("status"), "processing")
                await ledger.append(session, cart, "refund_reconciled", {"operation_id": row.id, "status": row.status})
            elif row.kind == "cancel" and row.status == "pending" and link.get("status") in {"cancelled", "expired"}:
                row.status = "succeeded"
            elif row.kind in {"cancel", "recover"} and row.status == "pending" and link.get("status") == "paid":
                row.status = "failed"
                row.details = {"message": "Payment captured before cancellation; review refund eligibility."}
            elif row.kind == "recover" and row.status == "pending" and link.get("status") in {"cancelled", "expired"}:
                # Recovery never creates a new charge automatically after uncertainty.
                row.status = "failed"
                row.details = {"message": "Old link closed; explicitly request recovery again."}
        await session.flush()
        state = await eligibility(session, cart)
        if state["refunded_paise"] >= cart.total_paise and cart.status == "test_paid":
            cart.status = "test_refunded"
        await session.commit()
        return await eligibility(session, cart)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        await session.rollback()
        raise HTTPException(503, "Provider reconciliation failed; no new charge or refund was submitted.") from None


async def execute(session: AsyncSession, shopper: ShopperSession, cart: ShoppingCart, body: ResolutionRequest) -> dict:
    if body.action == "reconcile":
        return await reconcile(session, cart)
    rows = await history(session, cart.id)
    existing = next((row for row in rows if row.request_key == body.request_key), None)
    if existing:
        if existing.kind != body.action or (body.amount_paise is not None and existing.amount_paise != body.amount_paise):
            raise HTTPException(409, "Request key already identifies a different operation.")
        return projection(existing)
    if not ledger.verify(await ledger.events(session, cart.id)):
        raise HTTPException(409, "Cart audit verification failed.")
    state = await eligibility(session, cart)
    if state["pending_operation"]:
        raise HTTPException(409, "Reconcile the pending operation before requesting another.")
    if not state.get("can_" + body.action):
        raise HTTPException(409, "The requested action is not eligible in this cart state.")
    if body.action == "return_review":
        operation = CommerceOperation(id=str(uuid4()), cart_id=cart.id, request_key=body.request_key,
            kind="return_review", status="review_required", amount_paise=0, provider_id=None,
            details={"reason": body.reason, "physical_stock_changed": False, "automatic_refund": False}, created_at=int(time.time()))
        session.add(operation)
        await ledger.append(session, cart, "return_review_requested", {"operation_id": operation.id, "reason": body.reason})
        await session.commit()
        return projection(operation)
    amount = (body.amount_paise or state["refundable_paise"]) if body.action == "refund" else 0
    if body.action == "refund" and amount > state["refundable_paise"]:
        raise HTTPException(422, "Refund exceeds the remaining captured balance.")
    if body.action == "recover":
        recovery_request = CartRequest(budget_paise=cart.budget_paise,
            items=[{"product_id": row["product_id"], "quantity": row["quantity"]} for row in cart.items])
        await carts.price_lines(session, cart.merchant_id, recovery_request, await carts.policy_for(session, cart.merchant_id))
    operation = CommerceOperation(id=str(uuid4()), cart_id=cart.id, request_key=body.request_key,
        kind=body.action, status="pending", amount_paise=amount, created_at=int(time.time()), details={})
    simulated = cart.status in {"simulated", "simulated_refunded"}
    if body.action == "refund" and not simulated:
        if amount < 100:
            raise HTTPException(422, "Razorpay test refunds require at least INR 1.00.")
        payments.require_test_provider()
        try:
            payment = await payments.captured_payment(cart, await payments.fetch_link(cart))
            if payment.get("amount_refunded", 0) != state["refunded_paise"]:
                raise HTTPException(409, "Provider refund balance differs; reconcile before continuing.")
            operation.details = {"payment_id": payment["id"]}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(503, "Could not verify captured test payment; no refund requested.") from None
    if body.action in {"cancel", "recover"} and cart.checkout_id and cart.status == "checkout_ready":
        payments.require_test_provider()
    session.add(operation)
    await ledger.append(session, cart, body.action + "_requested", {"operation_id": operation.id, "amount_paise": amount})
    await session.commit()  # Claim survives ambiguous provider failures.
    try:
        if body.action == "refund":
            if simulated:
                operation.status = "succeeded"
                operation.details = {"simulation": True}
            else:
                result = await payments.provider_request("POST", f"payments/{operation.details['payment_id']}/refund", {
                    "amount": amount, "notes": {"operation_id": operation.id, "cart_id": cart.id}})
                if result.get("amount") != amount or result.get("payment_id") != operation.details["payment_id"]:
                    raise ValueError("Invalid refund response")
                operation.provider_id = result["id"]
                operation.status = {"processed": "succeeded", "failed": "failed"}.get(result.get("status"), "processing")
            if operation.status == "succeeded" and state["refunded_paise"] + amount == cart.total_paise:
                cart.status = "simulated_refunded" if simulated else "test_refunded"
        else:
            if cart.checkout_id and cart.status == "checkout_ready":
                result = await payments.provider_request("POST", f"payment_links/{cart.checkout_id}/cancel")
                if result.get("id") != cart.checkout_id or result.get("status") != "cancelled":
                    raise ValueError("Test link cancellation not verified")
            cart.status = "cancelled"
            if body.action == "recover":
                request = CartRequest(budget_paise=cart.budget_paise,
                    items=[{"product_id": row["product_id"], "quantity": row["quantity"]} for row in cart.items])
                # Fresh prices and stock; this creates a new draft requiring new approval.
                fresh = await carts.create(session, shopper, request, commit=False)
                operation.details = {"recovered_cart_id": fresh.id, "requires_approval": True}
            operation.status = "succeeded"
        await ledger.append(session, cart, body.action + "_result", {"operation_id": operation.id,
            "status": operation.status, "amount_paise": amount, **operation.details})
        await session.commit()
        return projection(operation)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        await session.rollback()
        raise HTTPException(503, "Operation result is uncertain. Reconcile its status; do not submit a new request key.") from None
