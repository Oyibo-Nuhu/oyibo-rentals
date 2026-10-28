from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from ..database import get_db
from ..models import Alert, DamageClaim, Payment, Rental, User, lagos_now
from ..security import current_user
from ..services import (booking_window, build_quote, complete_rental, ensure_owner, is_vehicle_free,
                        licence_status, new_code, payment_amounts, rental_dict)
from .fleet import QuoteIn, normalize_start

router = APIRouter(prefix="/api/rentals", tags=["rentals"])


class BookingIn(QuoteIn):
    payment_plan: str = "full"


@router.post("")
def create_booking(data: BookingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not data.with_driver:
        lic = licence_status(db, user)
        if not lic["ok"]:
            raise HTTPException(403, f"Self-drive needs a valid full driver's licence. {lic['reason']}")
    start = normalize_start(data.start_at)
    row, q = build_quote(db, data.vehicle_id, data.mode, start, days=data.days, pickup=data.pickup,
                         dropoff=data.dropoff, destination=data.destination,
                         insurance_plan=data.insurance_plan, with_driver=data.with_driver)
    end = booking_window(data.mode, start, q)
    if not is_vehicle_free(db, row.id, start, end):
        raise HTTPException(409, "This vehicle is already booked for that time. Try another time or vehicle.")
    if data.payment_plan not in ("full", "installments"):
        raise HTTPException(422, "Unknown payment plan.")
    if data.payment_plan == "installments" and not (data.mode in (eng.FULL_DAY, eng.CROSS_COUNTRY) and data.days >= 7):
        raise HTTPException(422, "Pay small small is available for full-day or cross-country rentals of 7+ days.")

    rental = Rental(code=new_code(), user_id=user.id, vehicle_id=row.id, mode=data.mode,
                    pickup_key=(q.route or {}).get("pickup_key"), dropoff_key=(q.route or {}).get("dropoff_key"),
                    destination=data.destination if data.mode == eng.CROSS_COUNTRY else None,
                    start_at=start, end_at=end, with_driver=data.with_driver, insurance_plan=data.insurance_plan,
                    payment_plan=data.payment_plan, quote=q.as_dict(), total_due=round(q.total_due, 2))
    db.add(rental)
    db.flush()
    first_kind, first_amount = payment_amounts(q.total_due, q.security_deposit, data.payment_plan)[0]
    payment = Payment(rental_id=rental.id, reference=new_code("PAY"), amount=first_amount, kind=first_kind)
    db.add(payment)
    db.commit()
    return {"rental": rental_dict(rental), "payment": {"reference": payment.reference, "amount": payment.amount}}


@router.get("/mine")
def my_rentals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Rental).where(Rental.user_id == user.id).order_by(Rental.created_at.desc())).all()
    return [rental_dict(r) for r in rows if r.status != "pending_payment" or
            (lagos_now() - r.created_at).total_seconds() < 3600]


@router.get("/{code}")
def get_rental(code: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rental = ensure_owner(db.scalar(select(Rental).where(Rental.code == code)), user)
    return rental_dict(rental, include_track=True, db=db)


@router.post("/{code}/end")
def end_rental(code: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rental = ensure_owner(db.scalar(select(Rental).where(Rental.code == code)), user)
    settlement = complete_rental(db, rental)
    db.commit()
    return {"rental": rental_dict(rental), "settlement": settlement}


@router.post("/{code}/cancel")
def cancel_rental(code: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rental = ensure_owner(db.scalar(select(Rental).where(Rental.code == code)), user)
    if rental.status not in ("pending_payment", "reserved"):
        raise HTTPException(409, "Only unpaid or upcoming rentals can be cancelled.")
    refundable = rental.status == "reserved"
    rental.status = "cancelled"
    db.commit()
    msg = "Booking cancelled."
    if refundable:
        msg += " Your payment will be refunded to the original payment method."
    return {"message": msg}


class SosIn(BaseModel):
    message: str = Field(default="Emergency assistance requested.", max_length=300)


@router.post("/{code}/sos")
def sos(code: str, data: SosIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rental = ensure_owner(db.scalar(select(Rental).where(Rental.code == code)), user)
    if rental.status != "active":
        raise HTTPException(409, "SOS is available during an active rental.")
    where = f" at {rental.vehicle.lat:.4f}, {rental.vehicle.lng:.4f}" if rental.vehicle.lat else ""
    db.add(Alert(rental_id=rental.id, kind="sos",
                 message=f"SOS from {user.name} ({user.phone}){where}: {data.message.strip() or 'Help needed.'}"))
    db.commit()
    return {"message": "Our response team has been alerted and will call you. "
                       "For life-threatening emergencies, also call 112."}


class RateIn(BaseModel):
    rating: int = Field(ge=1, le=5)


@router.post("/{code}/rate")
def rate(code: str, data: RateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rental = ensure_owner(db.scalar(select(Rental).where(Rental.code == code)), user)
    if rental.status != "completed":
        raise HTTPException(409, "You can rate a trip after it ends.")
    rental.rating = data.rating
    db.commit()
    return {"message": "Thanks for rating your trip!"}


class ClaimIn(BaseModel):
    description: str = Field(min_length=5, max_length=1000)
    damage_cost: float = Field(gt=0, le=200_000_000)


@router.post("/{code}/claims")
def report_damage(code: str, data: ClaimIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rental = ensure_owner(db.scalar(select(Rental).where(Rental.code == code)), user)
    if rental.status not in ("active", "completed"):
        raise HTTPException(409, "Damage can be reported for active or completed rentals.")
    payout = eng.calculate_claim_payout(rental.insurance_plan, data.damage_cost)
    claim = DamageClaim(rental_id=rental.id, description=data.description.strip(), damage_cost=data.damage_cost,
                        insurer_pays=payout["insurer_pays"], customer_pays=payout["customer_pays"])
    db.add(claim)
    db.commit()
    return {"claim_id": claim.id, **payout, "status": claim.status}
