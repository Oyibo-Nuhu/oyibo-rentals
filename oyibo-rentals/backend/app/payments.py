"""Paystack integration with a built-in demo mode.

* With PAYSTACK_SECRET_KEY set (use an sk_test_ key while testing), customers
  are sent to Paystack's hosted checkout, which supports card, bank transfer,
  USSD and more. Card details never touch this app.
* Without a key, the app runs in demo mode: payments are simulated so the full
  flow can be tried without real money.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx

from .config import settings

PAYSTACK_API = "https://api.paystack.co"
CHANNELS = ["card", "bank_transfer", "ussd", "bank"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.paystack_secret}", "Content-Type": "application/json"}


def initialize(email: str, amount_naira: float, reference: str, metadata: dict) -> str:
    """Returns Paystack's hosted checkout URL."""
    payload = {
        "email": email,
        "amount": int(round(amount_naira * 100)),  # kobo
        "currency": "NGN",
        "reference": reference,
        "callback_url": f"{settings.public_url}/paystack/return",
        "channels": CHANNELS,
        "metadata": metadata,
    }
    response = httpx.post(f"{PAYSTACK_API}/transaction/initialize", json=payload, headers=_headers(), timeout=20)
    data = response.json()
    if response.status_code >= 400 or not data.get("status"):
        raise RuntimeError(data.get("message", "Could not start Paystack checkout."))
    return data["data"]["authorization_url"]


def verify(reference: str) -> tuple[bool, float, str]:
    """Returns (paid, amount_in_naira, channel)."""
    response = httpx.get(f"{PAYSTACK_API}/transaction/verify/{reference}", headers=_headers(), timeout=20)
    data = response.json()
    if response.status_code >= 400 or not data.get("status"):
        return False, 0.0, ""
    tx = data["data"]
    return tx.get("status") == "success", tx.get("amount", 0) / 100, tx.get("channel", "")


def valid_webhook(body: bytes, signature: str | None) -> bool:
    if not settings.paystack_secret or not signature:
        return False
    expected = hmac.new(settings.paystack_secret.encode(), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
