"""Glue between the database rows and the pure-Python rental engine."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import engine as eng
from .config import FRONTEND_DIR, PHOTO_DIR
from .locations import LAGOS_ZONES, get_zone, haversine_km
from .models import Alert, DriverLicense, Notification, Payment, Rental, TrackingPoint, User, Vehicle, iso, lagos_now

BLOCKING_STATUSES = ("reserved", "active")
POINTS_PER_1000_NAIRA = 1


def to_engine(row: Vehicle) -> eng.Vehicle:
    return eng.build_vehicle(row.tier, row.id, row.brand, row.model, row.year, row.daily_rate,
                             row.is_electric, row.seats, row.status == "available")


_photos = {"mtime": None, "data": {}}


def fleet_photos() -> dict:
    """credits.json written by scripts/fetch_vehicle_photos.py (and admin uploads), cached by mtime."""
    path = PHOTO_DIR / "credits.json"
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return {}
    if _photos["mtime"] != mtime:
        _photos.update(mtime=mtime, data=json.loads(path.read_text(encoding="utf-8")))
    return _photos["data"]


def save_photo_credit(vehicle_id: str, credit: dict) -> None:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    data = dict(fleet_photos())
    data[vehicle_id] = credit
    (PHOTO_DIR / "credits.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def vehicle_dict(row: Vehicle) -> dict:
    v = to_engine(row)
    photo = fleet_photos().get(row.id)
    if photo and not (PHOTO_DIR / f"{row.id}.jpg").exists():
        photo = None
    return {
        "photo": f"/static/{photo['file']}?v={int(_photos['mtime'] or 0)}" if photo else None,
        "photo_credit": {k: photo.get(k, "") for k in ("author", "license", "license_url", "source")} if photo else None,
        "allowed_modes": list(v.ALLOWED_MODES),
        "id": row.id, "tier": row.tier, "tier_label": v.TIER_LABEL, "brand": row.brand, "model": row.model,
        "year": row.year, "daily_rate": row.daily_rate, "hourly_route_rate": v.get_hourly_route_rate(),
        "is_electric": row.is_electric, "seats": row.seats, "plate": row.plate, "color": row.color,
        "status": row.status, "fuel_level": round(row.fuel_level), "odometer_km": round(row.odometer_km),
        "home_zone": LAGOS_ZONES[row.home_zone].name if row.home_zone in LAGOS_ZONES else row.home_zone,
        "security_deposit": v.SECURITY_DEPOSIT, "min_insurance": v.MIN_INSURANCE,
        "mileage_rate": v.MILEAGE_RATE, "speed_limit": v.get_speed_limit(),
        "lat": row.lat, "lng": row.lng,
    }


def rental_dict(r: Rental, include_track: bool = False, db: Session | None = None) -> dict:
    data = {
        "id": r.id, "code": r.code, "mode": r.mode, "status": r.status,
        "vehicle": vehicle_dict(r.vehicle), "customer": {"id": r.user.id, "name": r.user.name, "phone": r.user.phone},
        "pickup": LAGOS_ZONES[r.pickup_key].name if r.pickup_key else None,
        "dropoff": LAGOS_ZONES[r.dropoff_key].name if r.dropoff_key else None,
        "destination": (r.quote.get("route") or {}).get("destination") if r.mode == eng.CROSS_COUNTRY else None,
        "start_at": iso(r.start_at), "end_at": iso(r.end_at), "actual_end_at": iso(r.actual_end_at),
        "with_driver": r.with_driver, "insurance_plan": r.insurance_plan, "payment_plan": r.payment_plan,
        "quote": r.quote, "total_due": r.total_due, "settlement": r.settlement, "final_cost": r.final_cost,
        "distance_km": round(r.distance_km, 1), "speeding_events": r.speeding_events,
        "max_speed": round(r.max_speed, 1), "rating": r.rating, "created_at": iso(r.created_at),
        "amount_paid": round(sum(p.amount for p in r.payments if p.status == "success"), 2),
        "pending_payments": [{"reference": p.reference, "amount": p.amount, "kind": p.kind}
                             for p in r.payments if p.status == "pending" and p.kind != "booking"],
    }
    if include_track and db is not None:
        points = db.scalars(select(TrackingPoint).where(TrackingPoint.rental_id == r.id)
                            .order_by(TrackingPoint.ts.desc()).limit(120)).all()
        data["track"] = [{"ts": iso(p.ts), "lat": p.lat, "lng": p.lng, "speed": round(p.speed_kmh, 1),
                          "location": p.location, "over_limit": p.over_limit} for p in reversed(points)]
    return data


def new_code(prefix: str = "OY") -> str:
    return f"{prefix}-{secrets.token_hex(4).upper()}"


def booking_window(mode: str, start: datetime, quote: eng.Quote) -> datetime:
    if mode in (eng.ROUTE, eng.HALF_DAY):
        return start + timedelta(hours=quote.units)
    return start + timedelta(days=quote.units)


def is_vehicle_free(db: Session, vehicle_id: str, start: datetime, end: datetime, ignore_id: int | None = None) -> bool:
    stmt = select(Rental).where(Rental.vehicle_id == vehicle_id, Rental.status.in_(BLOCKING_STATUSES),
                                Rental.start_at < end, Rental.end_at > start)
    if ignore_id is not None:
        stmt = stmt.where(Rental.id != ignore_id)
    return db.scalars(stmt).first() is None


def build_quote(db: Session, vehicle_id: str, mode: str, start: datetime, **kwargs) -> tuple[Vehicle, eng.Quote]:
    row = db.get(Vehicle, vehicle_id)
    if row is None:
        raise HTTPException(404, "Vehicle not found.")
    if row.status == "maintenance":
        raise HTTPException(409, "This vehicle is in the workshop right now. Please pick another one.")
    if row.status == "unavailable":
        raise HTTPException(409, "This vehicle isn't available for booking right now. Please pick another one.")
    try:
        quote = eng.quote_rental(to_engine(row), mode, start, **kwargs)
    except ValueError as error:
        raise HTTPException(422, str(error))
    return row, quote


def payment_amounts(total_due: float, deposit: float, plan: str) -> list[tuple[str, float]]:
    """'Pay small small': deposit plus 40% now, remaining 60% before the rental ends."""
    if plan == "full":
        return [("booking", round(total_due, 2))]
    rest = total_due - deposit
    first = round(deposit + rest * 0.4, 2)
    return [("booking", first), ("installment", round(total_due - first, 2))]


def mark_payment_success(db: Session, payment: Payment, channel: str | None = None) -> Rental:
    """Idempotent: confirms a payment and moves the rental forward."""
    rental = payment.rental
    if payment.status == "success":
        return rental
    if payment.kind == "booking" and rental.status != "pending_payment":
        raise HTTPException(409, "This booking is no longer awaiting payment.")
    if payment.kind == "booking" and not is_vehicle_free(db, rental.vehicle_id, rental.start_at, rental.end_at, rental.id):
        payment.status = "failed"
        rental.status = "cancelled"
        db.commit()
        raise HTTPException(409, "Sorry, someone else just booked this vehicle for that time. "
                                 "Your payment has been marked for refund.")
    payment.status = "success"
    payment.paid_at = lagos_now()
    if channel:
        payment.channel = channel
    if payment.kind == "booking":
        rental.status = "reserved"
        if rental.payment_plan == "installments":
            db.add(Payment(rental_id=rental.id, reference=new_code("INS"), kind="installment",
                           amount=round(rental.total_due - payment.amount, 2), provider=payment.provider))
        start_due_rentals(db, [rental])
    rental.user.loyalty_points += int(payment.amount // 1000) * POINTS_PER_1000_NAIRA
    db.commit()
    return rental


def start_due_rentals(db: Session, rentals: list[Rental] | None = None) -> None:
    now = lagos_now()
    if rentals is None:
        rentals = db.scalars(select(Rental).where(Rental.status == "reserved", Rental.start_at <= now)).all()
    for r in rentals:
        if r.status == "reserved" and r.start_at <= now:
            r.status = "active"
            r.vehicle.status = "rented"
            start = get_zone(r.pickup_key) if r.pickup_key else LAGOS_ZONES.get(r.vehicle.home_zone)
            if start:
                r.vehicle.lat, r.vehicle.lng = start.lat, start.lng


def near(location: str) -> str:
    """'near Ikoyi', without doubling up when the place is already called 'Near Ikoyi'."""
    return location[0].lower() + location[1:] if location.lower().startswith("near ") else f"near {location}"


# The GPS simulator invents speeding all day long. In the demo, a customer gets at most this many automatic
# speeding notifications in total; after that only warnings an admin sends from Live GPS reach them.
# Real tracker pings (POST /api/tracking/{code}/ping) are never capped.
DEMO_AUTO_SPEEDING_NOTICES = 5


def record_tracking(db: Session, rental: Rental, location: str, lat: float, lng: float, speed: float,
                    when: datetime | None = None, simulated: bool = False) -> dict:
    """Validates with the engine's rules (empty location rejected, 100 km/h limit)."""
    if rental.status != "active":
        raise HTTPException(409, "Tracking is only available for active rentals.")
    try:
        reading = eng.validate_tracking_update(to_engine(rental.vehicle), location, speed)
    except ValueError as error:
        raise HTTPException(422, str(error))
    if not (3.5 <= lat <= 14.5 and 2.5 <= lng <= 15.0):
        raise HTTPException(422, "Coordinates must be inside Nigeria.")

    when = when or lagos_now()
    vehicle = rental.vehicle
    if vehicle.lat is not None:
        step = haversine_km(vehicle.lat, vehicle.lng, lat, lng)
        rental.distance_km += step
        vehicle.odometer_km += step
        vehicle.fuel_level = max(5.0, vehicle.fuel_level - step * 0.25)
    vehicle.lat, vehicle.lng = lat, lng
    rental.max_speed = max(rental.max_speed, reading["speed_kmh"])
    db.flush()   # make sure the last reading is visible even if it hasn't been committed yet
    previous = db.scalars(select(TrackingPoint).where(TrackingPoint.rental_id == rental.id)
                          .order_by(TrackingPoint.ts.desc(), TrackingPoint.id.desc()).limit(1)).first()
    db.add(TrackingPoint(rental_id=rental.id, ts=when, location=reading["location"], lat=lat, lng=lng,
                         speed_kmh=reading["speed_kmh"], over_limit=reading["over_speed_limit"]))
    message = f"Tracking update recorded at {when:%Y-%m-%d %H:%M:%S}."
    if reading["over_speed_limit"]:
        message = (f"Speed warning: {reading['speed_kmh']:.1f} km/h exceeds the "
                   f"{eng.SPEED_LIMIT_KMH} km/h limit {near(reading['location'])}.")
        # One incident per stretch over the limit: a reading counts only if the previous one was within it.
        if previous is None or not previous.over_limit:
            rental.speeding_events += 1
            db.add(Alert(rental_id=rental.id, kind="speeding", message=message, created_at=when))
            if not rental.with_driver and not (simulated and demo_notices_used_up(db, rental.user_id)):
                # our own drivers are managed by staff, so customers aren't told or charged for them
                notify_speeding(db, rental, reading["speed_kmh"], reading["location"], when)
    if vehicle.fuel_level < 15 and not vehicle.is_electric:
        recent = db.scalars(select(Alert).where(Alert.rental_id == rental.id, Alert.kind == "low_fuel")).first()
        if recent is None:
            db.add(Alert(rental_id=rental.id, kind="low_fuel", created_at=when,
                         message=f"{vehicle.brand} {vehicle.model} is below 15% fuel {near(reading['location'])}."))
    return {"over_speed_limit": reading["over_speed_limit"], "message": message}


def notify(db: Session, user_id: int, kind: str, title: str, body: str = "", rental_id: int | None = None,
           when: datetime | None = None) -> Notification:
    n = Notification(user_id=user_id, kind=kind, title=title, body=body, rental_id=rental_id,
                     created_at=when or lagos_now())
    db.add(n)
    return n


def demo_notices_used_up(db: Session, user_id: int) -> bool:
    db.flush()   # include notices added earlier in this same session
    sent = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id, Notification.kind == "speeding")) or 0
    return sent >= DEMO_AUTO_SPEEDING_NOTICES


def notify_speeding(db: Session, rental: Rental, speed: float, location: str, when: datetime) -> None:
    n, free, fee = rental.speeding_events, eng.SPEEDING_FREE_STRIKES, eng.SPEEDING_FEE
    where = f"{speed:.0f} km/h {near(location)}. The limit is {eng.SPEED_LIMIT_KMH} km/h."
    if n < free:
        title = f"Speeding warning {n} of {free}"
        body = f"{where} After {free} warnings, each further incident on this trip costs ₦{fee:,}."
    elif n == free:
        title = f"Final speeding warning ({n} of {free})"
        body = f"{where} From the next incident, ₦{fee:,} is charged each time, taken from your deposit."
    else:
        title = f"Speeding charge: ₦{fee:,}"
        body = (f"{where} That is incident {n} on this trip, so ₦{eng.speeding_charge(n):,.0f} in speeding "
                f"charges so far. Please slow down.")
    notify(db, rental.user_id, "speeding", title, body, rental.id, when)


def licence_status(db: Session, user: User) -> dict:
    """Whether this customer may book without a driver, and why not if they can't."""
    lic = db.scalar(select(DriverLicense).where(DriverLicense.user_id == user.id))
    if lic is None:
        return {"ok": False, "status": "missing", "reason": "Add your driver's licence on your profile to drive yourself."}
    if lic.status == "rejected":
        return {"ok": False, "status": "rejected", "reason": "Your licence was not accepted"
                + (f": {lic.review_note}" if lic.review_note else ".") + " Upload it again or add a driver."}
    if lic.expires_on.date() <= lagos_now().date():
        return {"ok": False, "status": "expired", "reason": "Your licence has expired. Upload your renewed licence or add a driver."}
    return {"ok": True, "status": lic.status, "reason": ""}


def licence_dict(lic: DriverLicense | None) -> dict | None:
    if lic is None:
        return None
    return {"id": lic.id, "number": lic.number, "state": lic.state, "expires_on": lic.expires_on.date().isoformat(),
            "status": lic.status, "review_note": lic.review_note, "has_image": bool(lic.image_file),
            "submitted_at": iso(lic.submitted_at), "reviewed_at": iso(lic.reviewed_at)}


def complete_rental(db: Session, rental: Rental, when: datetime | None = None) -> dict:
    if rental.status != "active":
        raise HTTPException(409, "Only active rentals can be ended.")
    when = when or lagos_now()
    settlement = eng.calculate_settlement(to_engine(rental.vehicle), rental.quote, rental.end_at, when,
                                          rental.distance_km, 0 if rental.with_driver else rental.speeding_events)
    rental.settlement = settlement
    rental.final_cost = settlement["final_cost"]
    rental.actual_end_at = when
    rental.status = "completed"
    rental.vehicle.status = "available"
    if rental.dropoff_key:
        rental.vehicle.home_zone = rental.dropoff_key
    if settlement["balance_due"] > 0:
        db.add(Payment(rental_id=rental.id, reference=new_code("BAL"), kind="balance",
                       amount=settlement["balance_due"], provider="demo"))
    return settlement


def ensure_owner(rental: Rental | None, user: User) -> Rental:
    if rental is None or (rental.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Rental not found.")
    return rental
