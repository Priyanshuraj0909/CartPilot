"""Razorpay test-mode links only. Ambiguous network outcomes are never retried blindly."""
from urllib.parse import urlparse
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
