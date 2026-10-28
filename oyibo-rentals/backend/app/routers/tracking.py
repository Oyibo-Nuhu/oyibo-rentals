from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert, Rental, TrackingPoint, User, iso, lagos_now
from ..security import current_user
from ..services import ensure_owner, record_tracking, start_due_rentals

router = APIRouter(prefix="/api/tracking", tags=["tracking"])


@router.get("/live")
def live(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Active rentals with their latest position. Admins see the whole fleet."""
    start_due_rentals(db)
    db.commit()
    stmt = select(Rental).where(Rental.status == "active")
    if user.role != "admin":
        stmt = stmt.where(Rental.user_id == user.id)
    now = lagos_now()
    out = []
    for r in db.scalars(stmt).all():
        last = db.scalars(select(TrackingPoint).where(TrackingPoint.rental_id == r.id)
                          .order_by(TrackingPoint.ts.desc()).limit(1)).first()
        out.append({
            "code": r.code, "mode": r.mode, "customer": r.user.name if user.role == "admin" else None,
            "vehicle": f"{r.vehicle.brand} {r.vehicle.model}", "vehicle_id": r.vehicle.id, "tier": r.vehicle.tier,
            "plate": r.vehicle.plate, "lat": r.vehicle.lat, "lng": r.vehicle.lng,
            "speed": round(last.speed_kmh, 1) if last else 0, "location": last.location if last else "Awaiting signal",
            "over_limit": bool(last and last.over_limit), "speeding_events": r.speeding_events,
            "distance_km": round(r.distance_km, 1), "fuel_level": round(r.vehicle.fuel_level),
            "is_electric": r.vehicle.is_electric, "end_at": iso(r.end_at),
            "overdue": r.end_at < now, "last_seen": iso(last.ts) if last else None,
        })
    return out


@router.get("/alerts")
def alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(40)
    if user.role != "admin":
        stmt = stmt.join(Rental).where(Rental.user_id == user.id)
    return [{"id": a.id, "kind": a.kind, "message": a.message, "resolved": a.resolved,
             "rental": a.rental.code, "created_at": iso(a.created_at)} for a in db.scalars(stmt).all()]


class PingIn(BaseModel):
    location: str
    lat: float
    lng: float
    speed_kmh: float


@router.post("/{code}/ping")
def ping(code: str, data: PingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """For a GPS device or driver app. Empty locations are rejected; >100 km/h raises an alert."""
    rental = ensure_owner(db.scalar(select(Rental).where(Rental.code == code)), user)
    result = record_tracking(db, rental, data.location, data.lat, data.lng, data.speed_kmh)
    db.commit()
    return result
