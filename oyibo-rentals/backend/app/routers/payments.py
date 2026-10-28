from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import payments as paystack
from ..config import settings
from ..database import get_db
from ..models import Payment, User
from ..security import current_user
from ..services import ensure_owner, mark_payment_success, rental_dict

router = APIRouter(prefix="/api/payments", tags=["payments"])


def _payment(db: Session, reference: str, user: User) -> Payment:
    payment = db.scalar(select(Payment).where(Payment.reference == reference))
    if payment is None:
        raise HTTPException(404, "Payment not found.")
    ensure_owner(payment.rental, user)
    return payment


def _result(payment: Payment) -> dict:
    rental = payment.rental
    return {"status": payment.status, "amount": payment.amount, "kind": payment.kind,
            "points_earned": int(payment.amount // 1000), "rental": rental_dict(rental),
            "loyalty_points": rental.user.loyalty_points}


@router.post("/{reference}/checkout")
def checkout(reference: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    payment = _payment(db, reference, user)
    if payment.status == "success":
        return {"mode": "done", **_result(payment)}
    if not settings.payments_live:
        return {"mode": "demo", "amount": payment.amount, "reference": reference}
    try:
        url = paystack.initialize(user.email, payment.amount, reference,
                                  {"rental": payment.rental.code, "kind": payment.kind})
    except Exception as error:  # network or Paystack error
        raise HTTPException(502, f"Payment provider error: {error}")
    payment.provider = "paystack"
    db.commit()
    return {"mode": "paystack", "url": url, "reference": reference}


class DemoConfirmIn(BaseModel):
    channel: str = "card"


@router.post("/{reference}/demo-confirm")
def demo_confirm(reference: str, data: DemoConfirmIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    if settings.payments_live:
        raise HTTPException(403, "Demo payments are disabled when Paystack is configured.")
    payment = _payment(db, reference, user)
    if data.channel not in ("card", "bank_transfer", "ussd"):
        raise HTTPException(422, "Unknown payment channel.")
    mark_payment_success(db, payment, data.channel)
    return _result(payment)


@router.get("/{reference}/verify")
def verify(reference: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    payment = _payment(db, reference, user)
    if payment.status != "success" and settings.payments_live:
        paid, amount, channel = paystack.verify(reference)
        if paid and amount + 0.01 >= payment.amount:
            mark_payment_success(db, payment, channel)
    return _result(payment)


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not paystack.valid_webhook(body, request.headers.get("x-paystack-signature")):
        raise HTTPException(401, "Invalid signature.")
    event = json.loads(body)
    if event.get("event") == "charge.success":
        tx = event.get("data", {})
        payment = db.scalar(select(Payment).where(Payment.reference == tx.get("reference")))
        if payment and payment.status != "success" and tx.get("amount", 0) / 100 + 0.01 >= payment.amount:
            try:
                mark_payment_success(db, payment, tx.get("channel"))
            except HTTPException:
                pass
    return {"ok": True}
