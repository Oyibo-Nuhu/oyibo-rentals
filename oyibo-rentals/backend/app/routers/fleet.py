from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from ..config import settings
from ..database import get_db
from ..locations import INTERSTATE_DESTINATIONS, LAGOS_ZONES, is_peak
from ..models import Vehicle, lagos_now
from ..services import build_quote, is_vehicle_free, booking_window, vehicle_dict

router = APIRouter(prefix="/api", tags=["fleet"])


@router.get("/meta")
def meta():
    return {
        "app_name": settings.app_name,
        "payments_mode": "paystack" if settings.payments_live else "demo",
        "now": lagos_now().isoformat() + "+01:00",
        "peak_now": is_peak(lagos_now()),
        "zones": [{"key": z.key, "name": z.name, "lat": z.lat, "lng": z.lng, "kind": z.kind}
                  for z in LAGOS_ZONES.values()],
        "destinations": [{"key": k, "name": v[0], "distance_km": v[1]} for k, v in INTERSTATE_DESTINATIONS.items()],
        "tiers": [{"key": t, "label": eng.TIER_CLASSES[t].TIER_LABEL,
                   "deposit": eng.TIER_CLASSES[t].SECURITY_DEPOSIT} for t in eng.TIER_ORDER],
        "insurance": eng.INSURANCE_PLANS,
        "speed_limit": eng.SPEED_LIMIT_KMH,
        "speeding_policy": {"free_strikes": eng.SPEEDING_FREE_STRIKES, "fee": eng.SPEEDING_FEE},
        "vat_rate": eng.VAT_RATE,
        "map": {"tile_url": settings.map_tile_url, "attribution": settings.map_attribution},
    }


@router.get("/fleet")
def list_fleet(tier: str | None = None, q: str | None = None, electric: bool | None = None,
               db: Session = Depends(get_db)):
    rows = db.scalars(select(Vehicle).order_by(Vehicle.daily_rate.desc())).all()
    if tier:
        rows = [r for r in rows if r.tier == tier]
    if electric is not None:
        rows = [r for r in rows if r.is_electric == electric]
    if q and q.strip():
        # Same matching as the original RentalSystem.search_vehicles()
        term = q.strip().lower()
        rows = [r for r in rows if term in r.brand.lower() or term in r.model.lower()
                or term in r.tier.lower() or term in r.id.lower()
                or term in eng.TIER_CLASSES[r.tier].TIER_LABEL.lower()]
    order = {t: i for i, t in enumerate(eng.TIER_ORDER)}
    rows.sort(key=lambda r: (order.get(r.tier, 99), -r.daily_rate))
    return [vehicle_dict(r) for r in rows]


@router.get("/fleet/{vehicle_id}")
def get_vehicle(vehicle_id: str, db: Session = Depends(get_db)):
    row = db.get(Vehicle, vehicle_id)
    if row is None:
        raise HTTPException(404, "Vehicle not found.")
    return vehicle_dict(row)


class QuoteIn(BaseModel):
    vehicle_id: str
    mode: str
    start_at: datetime | None = None
    days: int = 1
    pickup: str | None = None
    dropoff: str | None = None
    destination: str | None = None
    insurance_plan: str = "basic"
    with_driver: bool = False


def normalize_start(start: datetime | None) -> datetime:
    now = lagos_now()
    if start is None:
        return now
    if start.tzinfo is not None:
        from zoneinfo import ZoneInfo
        start = start.astimezone(ZoneInfo("Africa/Lagos")).replace(tzinfo=None)
    start = start.replace(second=0, microsecond=0)
    if start < now.replace(second=0) and (now - start).total_seconds() > 300:
        raise HTTPException(422, "Start time cannot be in the past.")
    if (start - now).days > 30:
        raise HTTPException(422, "Bookings can be made up to 30 days ahead.")
    return max(start, now)


@router.post("/quote")
def quote(data: QuoteIn, db: Session = Depends(get_db)):
    start = normalize_start(data.start_at)
    row, q = build_quote(db, data.vehicle_id, data.mode, start, days=data.days, pickup=data.pickup,
                         dropoff=data.dropoff, destination=data.destination,
                         insurance_plan=data.insurance_plan, with_driver=data.with_driver)
    end = booking_window(data.mode, start, q)
    result = q.as_dict()
    result["start_at"] = start.isoformat() + "+01:00"
    result["end_at"] = end.isoformat() + "+01:00"
    result["available"] = is_vehicle_free(db, row.id, start, end)
    result["installments_allowed"] = data.mode in (eng.FULL_DAY, eng.CROSS_COUNTRY) and data.days >= 7
    return result
