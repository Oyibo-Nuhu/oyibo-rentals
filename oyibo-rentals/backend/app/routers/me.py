"""The signed-in customer's own account: profile, password, notifications and driver's licence."""

from __future__ import annotations

import secrets
from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import engine as eng
from ..config import LICENCE_DIR
from ..database import get_db
from ..models import DriverLicense, Notification, Rental, User, iso, lagos_now
from ..security import current_user, hash_password, verify_password
from ..services import licence_dict, licence_status
from .auth import user_out

router = APIRouter(prefix="/api/me", tags=["me"])
MAX_IMAGE_BYTES = 6 * 1024 * 1024


# ---------- profile ----------

class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=20)

    @field_validator("name", "phone")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cannot be empty")
        return value.strip()


@router.get("")
def profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    done = db.scalars(select(Rental).where(Rental.user_id == user.id, Rental.status == "completed")).all()
    booked = db.scalar(select(func.count()).select_from(Rental).where(
        Rental.user_id == user.id, Rental.status.in_(("reserved", "active", "completed")))) or 0
    lic = db.scalar(select(DriverLicense).where(DriverLicense.user_id == user.id))
    return {
        "user": user_out(user),
        "member_since": iso(user.created_at),
        "stats": {
            "trips": int(booked),
            "completed": len(done),
            "km": round(sum(r.distance_km for r in done), 1),
            "spent": round(sum(r.final_cost or r.total_due for r in done), 2),
            "speeding_incidents": sum(r.speeding_events for r in done if not r.with_driver),
            "speeding_charges": round(sum((r.settlement or {}).get("speeding_charge", 0) for r in done), 2),
        },
        "licence": licence_dict(lic),
        "self_drive": licence_status(db, user),
        "speeding_policy": {"free_strikes": eng.SPEEDING_FREE_STRIKES, "fee": eng.SPEEDING_FEE,
                            "limit_kmh": eng.SPEED_LIMIT_KMH},
    }


@router.put("")
def update_profile(data: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.name, user.phone = data.name, data.phone
    db.commit()
    return user_out(user)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


@router.post("/password")
def change_password(data: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(403, "Your current password is incorrect.")
    if data.current_password == data.new_password:
        raise HTTPException(422, "Choose a new password that is different from the current one.")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Password changed."}


# ---------- notifications ----------

@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(50)).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read.is_(False))) or 0
    codes = {}
    ids = {n.rental_id for n in rows if n.rental_id}
    if ids:
        codes = dict(db.execute(select(Rental.id, Rental.code).where(Rental.id.in_(ids))).all())
    return {"unread": int(unread), "items": [
        {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "read": n.read,
         "rental": codes.get(n.rental_id), "created_at": iso(n.created_at)} for n in rows]}


class ReadIn(BaseModel):
    ids: list[int] | None = None   # None = mark everything read


@router.post("/notifications/read")
def mark_read(data: ReadIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))
    if data.ids:
        stmt = stmt.where(Notification.id.in_(data.ids))
    db.execute(stmt.values(read=True))
    db.commit()
    return {"ok": True}


# ---------- driver's licence ----------

@router.get("/licence")
def my_licence(user: User = Depends(current_user), db: Session = Depends(get_db)):
    lic = db.scalar(select(DriverLicense).where(DriverLicense.user_id == user.id))
    return {"licence": licence_dict(lic), "self_drive": licence_status(db, user)}


@router.post("/licence")
async def submit_licence(kind: str = Form(...), number: str = Form(...), expires_on: date = Form(...),
                         state: str = Form(""), file: UploadFile = File(...),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Upload a photo of the licence with its details. Learner's permits and expired licences are refused."""
    try:
        clean = eng.validate_driver_licence(kind, number, expires_on, lagos_now().date())
    except ValueError as error:
        raise HTTPException(422, str(error))
    raw = await file.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "That photo is too large. The limit is 6 MB.")
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(BytesIO(raw))).convert("RGB")
    except Exception:
        raise HTTPException(422, "That file isn't a photo we can read. Use a JPG, PNG or WebP picture of your licence.")
    if img.width > 1600:
        img = img.resize((1600, round(img.height * 1600 / img.width)))

    LICENCE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{user.id}-{secrets.token_hex(8)}.jpg"
    img.save(LICENCE_DIR / name, "JPEG", quality=85)   # re-encoding also drops the phone's EXIF data (GPS etc.)

    lic = db.scalar(select(DriverLicense).where(DriverLicense.user_id == user.id))
    if lic is None:
        lic = DriverLicense(user_id=user.id, number=clean, expires_on=lagos_now())
        db.add(lic)
    elif lic.image_file:
        (LICENCE_DIR / lic.image_file).unlink(missing_ok=True)
    lic.number, lic.state = clean, state.strip()[:40]
    lic.expires_on = lagos_now().replace(year=expires_on.year, month=expires_on.month, day=expires_on.day,
                                         hour=0, minute=0, second=0)
    lic.image_file, lic.status, lic.review_note = name, "submitted", ""
    lic.submitted_at, lic.reviewed_at = lagos_now(), None
    db.commit()
    return {"licence": licence_dict(lic), "self_drive": licence_status(db, user)}
