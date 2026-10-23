"""Razorpay test-mode links only. Ambiguous network outcomes are never retried blindly."""
from urllib.parse import urlparse
import re
import httpx
from fastapi import HTTPException
from app.core.config import settings
from app.models.commerce import ShoppingCart


def require_test_provider() -> None:
    if not settings.BUYER_RAZORPAY_TEST_ENABLED or not settings.RAZORPAY_KEY_ID.startswith("rzp_test_") or not settings.RAZORPAY_KEY_SECRET.get_secret_value():
        raise HTTPException(503, "Razorpay test checkout is not configured.")


async def create_test_link(cart: ShoppingCart) -> tuple[str, str]:
    require_test_provider()
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        result = await client.post("https://api.razorpay.com/v1/payment_links/",
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET.get_secret_value()),
            json={"amount": cart.total_paise, "currency": "INR", "accept_partial": False,
                  "reference_id": cart.id, "description": "CartPilot test checkout",
                  "expire_by": cart.expires_at,
                  "notify": {"sms": False, "email": False}, "reminder_enable": False,
                  "notes": {"cart_id": cart.id}})
        result.raise_for_status()
        data = result.json()
        link_id, url = data["id"], data["short_url"]
        parsed = urlparse(url)
        if not isinstance(link_id, str) or not link_id.startswith("plink_") or len(link_id) > 100 or parsed.scheme != "https" or parsed.hostname != "rzp.io" or parsed.username or parsed.password or len(url) > 500 or data.get("amount") != cart.total_paise or data.get("currency") != "INR":
            raise ValueError("Invalid provider response")
        return link_id, url


async def provider_request(method: str, path: str, body: dict | None = None) -> dict:
    require_test_provider()
    if not re.fullmatch(r"(?:payment_links|payments|refunds)(?:/[a-zA-Z0-9_-]+){0,2}/?", path):
        raise ValueError("Invalid provider path")
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.request(method, "https://api.razorpay.com/v1/" + path,
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET.get_secret_value()),
            **({"json": body} if body is not None else {}))
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid provider response")
        return data


async def fetch_link(cart: ShoppingCart) -> dict:
    if cart.checkout_id:
        data = await provider_request("GET", f"payment_links/{cart.checkout_id}")
    else:
        collection = await provider_request("GET", "payment_links/")
        matches = [row for row in collection.get("items", [])[:100] if row.get("reference_id") == cart.id]
        if len(matches) != 1:
            raise ValueError("Checkout reference requires provider review")
        data = matches[0]
    if data.get("reference_id") != cart.id or data.get("currency") != "INR" or data.get("amount") != cart.total_paise:
        raise ValueError("Provider checkout does not match cart")
    if not isinstance(data.get("id"), str) or not re.fullmatch(r"plink_[a-zA-Z0-9]+", data["id"]):
        raise ValueError("Invalid checkout identity")
    return data


async def captured_payment(cart: ShoppingCart, link: dict) -> dict:
    if link.get("status") != "paid" or link.get("amount_paid") != cart.total_paise:
        raise ValueError("Full payment has not been captured")
    candidates = [row.get("payment_id") for row in link.get("payments", []) if row.get("payment_id")]
    if len(candidates) != 1 or not re.fullmatch(r"pay_[a-zA-Z0-9]+", candidates[0]):
        raise ValueError("Payment needs provider review")
    payment = await provider_request("GET", f"payments/{candidates[0]}")
    if payment.get("id") != candidates[0] or payment.get("amount") != cart.total_paise or payment.get("currency") != "INR" or payment.get("status") not in {"captured", "refunded"}:
        raise ValueError("Captured payment does not match checkout")
    return payment
