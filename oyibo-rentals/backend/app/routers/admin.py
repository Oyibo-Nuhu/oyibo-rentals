from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import analytics
from .. import engine as eng
from ..database import get_db
from ..locations import LAGOS_ZONES
from ..config import LICENCE_DIR
from ..models import Alert, DamageClaim, DriverLicense, Rental, User, Vehicle, iso, lagos_now
from ..security import admin_user
from ..services import PHOTO_DIR, licence_dict, notify, rental_dict, save_photo_credit, vehicle_dict

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/analytics")
def analytics_report(start: date | None = None, end: date | None = None, tiers: str = "", modes: str = "",
                     zone: str | None = None, db: Session = Depends(get_db)):
    """Filters apply to every number on the dashboard. tiers/modes are comma-separated keys."""
    split = lambda v: [x for x in v.split(",") if x] or None  # noqa: E731
    if start and end and start > end:
        raise HTTPException(422, "Start date must be before end date.")
    return analytics.full_report(db, start=start, end=end, tiers=split(tiers), modes=split(modes), zone=zone or None)


@router.post("/analytics/upload")
async def analyze_csv(file: UploadFile = File(...)):
    """The original dashboard's CSV analysis, same required columns and checks."""
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "CSV files must be 10 MB or smaller.")
    try:
        df = analytics.standardize_rental_data(pd.read_csv(BytesIO(raw)))
    except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as error:
        raise HTTPException(422, f"Could not analyze the CSV: {error}")
    return analytics.core_report(df)


@router.get("/analytics/export.csv")
def export(db: Session = Depends(get_db)):
    return Response(analytics.export_csv(db), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=oyibo_rentals_export.csv"})


@router.get("/rentals")
def all_rentals(status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    stmt = select(Rental).order_by(Rental.created_at.desc()).limit(min(limit, 500))
    if status:
        stmt = stmt.where(Rental.status == status)
    return [rental_dict(r) for r in db.scalars(stmt).all()]


@router.post("/rentals/{code}/end")
def force_end(code: str, db: Session = Depends(get_db)):
    from ..services import complete_rental
    rental = db.scalar(select(Rental).where(Rental.code == code))
    if rental is None:
        raise HTTPException(404, "Rental not found.")
    settlement = complete_rental(db, rental)
    db.commit()
    return settlement


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found.")
    alert.resolved = True
    db.commit()
    return {"ok": True}


class VehicleIn(BaseModel):
    id: str = Field(min_length=2, max_length=20)
    tier: str
    brand: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=60)
    year: int = Field(ge=1990, le=2030)
    daily_rate: float | None = Field(default=None, gt=0)
    is_electric: bool = False
    seats: int = Field(default=4, ge=1, le=60)
    plate: str = ""
    color: str = ""
    home_zone: str = "ikeja"


@router.post("/fleet")
def add_vehicle(data: VehicleIn, db: Session = Depends(get_db)):
    """Mirrors RentalSystem.add_vehicle(): duplicate IDs are rejected."""
    vid = data.id.strip().upper()
    if db.get(Vehicle, vid):
        raise HTTPException(409, "A vehicle with this ID already exists.")
    if data.home_zone not in LAGOS_ZONES:
        raise HTTPException(422, "Unknown home location.")
    try:
        v = eng.build_vehicle(data.tier, vid, data.brand.strip(), data.model.strip(), data.year, data.daily_rate,
                              data.is_electric, data.seats)
    except ValueError as error:
        raise HTTPException(422, str(error))
    zone = LAGOS_ZONES[data.home_zone]
    row = Vehicle(id=vid, tier=data.tier, brand=v.brand, model=v.model, year=v.year, daily_rate=v.get_daily_rate(),
                  is_electric=data.is_electric, seats=data.seats, plate=data.plate.strip().upper(),
                  color=data.color.strip(), home_zone=data.home_zone, lat=zone.lat, lng=zone.lng)
    db.add(row)
    db.commit()
    return {"message": f"{v.vehicle_type()} {v.brand} {v.model} added successfully.", "vehicle": vehicle_dict(row)}


MAX_PHOTO_BYTES = 6 * 1024 * 1024


@router.post("/fleet/{vehicle_id}/photo")
async def upload_vehicle_photo(vehicle_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Replace a vehicle's photo with one you took. Saved as a resized JPEG next to the fetched photos."""
    row = db.get(Vehicle, vehicle_id)
    if row is None:
        raise HTTPException(404, "Vehicle not found.")
    raw = await file.read(MAX_PHOTO_BYTES + 1)
    if len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo is too large. The limit is 6 MB.")
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(BytesIO(raw))).convert("RGB")
    except Exception:
        raise HTTPException(422, "That file isn't an image we can read. Use a JPG, PNG or WebP photo.")
    if img.width > 960:
        img = img.resize((960, round(img.height * 960 / img.width)))
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    img.save(PHOTO_DIR / f"{row.id}.jpg", "JPEG", quality=84, optimize=True, progressive=True)
    save_photo_credit(row.id, {"file": f"img/fleet/{row.id}.jpg", "title": file.filename or "upload",
                               "author": "Oyibo Rentals", "license": "All rights reserved", "license_url": "", "source": ""})
    return vehicle_dict(row)


VEHICLE_STATUSES = ("available", "unavailable", "maintenance")


class VehicleStatusIn(BaseModel):
    status: str


@router.post("/fleet/{vehicle_id}/status")
def set_vehicle_status(vehicle_id: str, data: VehicleStatusIn, db: Session = Depends(get_db)):
    row = db.get(Vehicle, vehicle_id)
    if row is None:
        raise HTTPException(404, "Vehicle not found.")
    if data.status not in VEHICLE_STATUSES:
        raise HTTPException(422, "Status must be available, unavailable or maintenance.")
    if row.status == "rented":
        raise HTTPException(409, "End the active rental before changing this vehicle's status.")
    if data.status == "available" and row.status == "maintenance":
        row.fuel_level = 100   # back from the workshop serviced and refuelled
    row.status = data.status
    db.commit()
    upcoming = db.scalars(select(Rental).where(Rental.vehicle_id == row.id, Rental.status == "reserved")).all()
    return {**vehicle_dict(row), "upcoming_bookings": [r.code for r in upcoming]}


class VehicleRateIn(BaseModel):
    daily_rate: float = Field(gt=0, le=50_000_000)


@router.post("/fleet/{vehicle_id}/rate")
def set_vehicle_rate(vehicle_id: str, data: VehicleRateIn, db: Session = Depends(get_db)):
    """Change a vehicle's daily rate. Hourly route, half-day and cross-country prices follow from it.
    Existing bookings keep the price they were quoted."""
    row = db.get(Vehicle, vehicle_id)
    if row is None:
        raise HTTPException(404, "Vehicle not found.")
    row.daily_rate = round(data.daily_rate, 2)
    db.commit()
    return vehicle_dict(row)


@router.get("/claims")
def claims(db: Session = Depends(get_db)):
    rows = db.scalars(select(DamageClaim).order_by(DamageClaim.created_at.desc()).limit(200)).all()
    return [{"id": c.id, "rental": c.rental.code, "customer": c.rental.user.name,
             "vehicle": f"{c.rental.vehicle.brand} {c.rental.vehicle.model}", "plan": c.rental.insurance_plan,
             "description": c.description, "damage_cost": c.damage_cost, "insurer_pays": c.insurer_pays,
             "customer_pays": c.customer_pays, "status": c.status, "created_at": iso(c.created_at)} for c in rows]


class ClaimDecisionIn(BaseModel):
    status: str


@router.post("/claims/{claim_id}")
def decide_claim(claim_id: int, data: ClaimDecisionIn, db: Session = Depends(get_db)):
    claim = db.get(DamageClaim, claim_id)
    if claim is None:
        raise HTTPException(404, "Claim not found.")
    if data.status not in ("approved", "rejected"):
        raise HTTPException(422, "Status must be approved or rejected.")
    claim.status = data.status
    db.commit()
    return {"ok": True}


@router.get("/users")
def users(db: Session = Depends(get_db)):
    rows = db.scalars(select(User).order_by(User.created_at.desc()).limit(300)).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role, "points": u.loyalty_points,
             "trips": len(u.rentals), "demo": u.is_demo, "joined": iso(u.created_at)} for u in rows]


# ---------- driver's licences ----------

@router.get("/licences")
def licences(db: Session = Depends(get_db)):
    order = {"submitted": 0, "rejected": 1, "verified": 2}
    rows = db.scalars(select(DriverLicense)).all()
    rows.sort(key=lambda l: (order.get(l.status, 9), -l.submitted_at.timestamp()))
    return [{**licence_dict(l), "customer": l.user.name, "email": l.user.email, "phone": l.user.phone,
             "expired": l.expires_on.date() <= lagos_now().date()} for l in rows]


@router.get("/licences/{licence_id}/image")
def licence_image(licence_id: int, db: Session = Depends(get_db)):
    lic = db.get(DriverLicense, licence_id)
    if lic is None or not lic.image_file or not (LICENCE_DIR / lic.image_file).is_file():
        raise HTTPException(404, "No photo on file for this licence.")
    return FileResponse(LICENCE_DIR / lic.image_file, media_type="image/jpeg",
                        headers={"Cache-Control": "private, no-store"})


class LicenceReviewIn(BaseModel):
    status: str
    note: str = Field("", max_length=300)


@router.post("/licences/{licence_id}")
def review_licence(licence_id: int, data: LicenceReviewIn, db: Session = Depends(get_db)):
    lic = db.get(DriverLicense, licence_id)
    if lic is None:
        raise HTTPException(404, "Licence not found.")
    if data.status not in ("verified", "rejected"):
        raise HTTPException(422, "Status must be verified or rejected.")
    if data.status == "rejected" and not data.note.strip():
        raise HTTPException(422, "Say why the licence was rejected, so the customer can fix it.")
    lic.status, lic.review_note, lic.reviewed_at = data.status, data.note.strip(), lagos_now()
    if data.status == "verified":
        notify(db, lic.user_id, "licence", "Your driver's licence is verified", "You can book any vehicle and drive it yourself.")
    else:
        notify(db, lic.user_id, "licence", "Your driver's licence wasn't accepted",
               f"{lic.review_note} Upload a clearer photo or a valid full licence on your profile, or add a driver when you book.")
    db.commit()
    return licence_dict(lic)


# ---------- message a driver ----------

class WarnIn(BaseModel):
    message: str = Field("", max_length=400)


@router.post("/rentals/{code}/warn")
def warn_driver(code: str, data: WarnIn, db: Session = Depends(get_db)):
    """Send the customer on this rental a speeding reminder (or any note) from the control room."""
    rental = db.scalar(select(Rental).where(Rental.code == code))
    if rental is None:
        raise HTTPException(404, "Rental not found.")
    left = max(0, eng.SPEEDING_FREE_STRIKES - rental.speeding_events)
    body = data.message.strip() or (
        f"Our control room has seen you above {eng.SPEED_LIMIT_KMH} km/h. You have {left} free warning"
        f"{'s' if left != 1 else ''} left on this trip; after that, each incident costs ₦{eng.SPEEDING_FEE:,}."
        if left else
        f"Our control room has seen you above {eng.SPEED_LIMIT_KMH} km/h. Each further incident costs ₦{eng.SPEEDING_FEE:,}.")
    notify(db, rental.user_id, "staff", "Message from the Oyibo control room", body, rental.id)
    db.commit()
    return {"message": f"Sent to {rental.user.name}."}
