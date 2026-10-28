from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

LAGOS = ZoneInfo("Africa/Lagos")


def lagos_now() -> datetime:
    """Naive Lagos local time. Lagos has no daylight saving, so this is stable."""
    return datetime.now(LAGOS).replace(tzinfo=None, microsecond=0)


def iso(value: datetime | None) -> str | None:
    return None if value is None else value.replace(microsecond=0).isoformat() + "+01:00"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="customer")
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0)
    referral_code: Mapped[str] = mapped_column(String(20), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lagos_now)
    rentals: Mapped[list["Rental"]] = relationship(back_populates="user")


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    tier: Mapped[str] = mapped_column(String(20), index=True)
    brand: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(60))
    year: Mapped[int] = mapped_column(Integer)
    daily_rate: Mapped[float] = mapped_column(Float)
    is_electric: Mapped[bool] = mapped_column(Boolean, default=False)
    seats: Mapped[int] = mapped_column(Integer, default=4)
    plate: Mapped[str] = mapped_column(String(20), default="")
    color: Mapped[str] = mapped_column(String(30), default="")
    status: Mapped[str] = mapped_column(String(20), default="available")  # available|rented|maintenance
    fuel_level: Mapped[float] = mapped_column(Float, default=100)        # percent, or battery for EVs
    odometer_km: Mapped[float] = mapped_column(Float, default=0)
    home_zone: Mapped[str] = mapped_column(String(40), default="ikeja")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lagos_now)


class Rental(Base):
    __tablename__ = "rentals"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending_payment", index=True)
    pickup_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dropoff_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(40), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    with_driver: Mapped[bool] = mapped_column(Boolean, default=False)
    insurance_plan: Mapped[str] = mapped_column(String(20), default="basic")
    payment_plan: Mapped[str] = mapped_column(String(20), default="full")  # full|installments
    quote: Mapped[dict] = mapped_column(JSON)
    total_due: Mapped[float] = mapped_column(Float)
    settlement: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_km: Mapped[float] = mapped_column(Float, default=0)
    speeding_events: Mapped[int] = mapped_column(Integer, default=0)
    max_speed: Mapped[float] = mapped_column(Float, default=0)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lagos_now)

    user: Mapped[User] = relationship(back_populates="rentals")
    vehicle: Mapped[Vehicle] = relationship()
    payments: Mapped[list["Payment"]] = relationship(back_populates="rental")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    rental_id: Mapped[int] = mapped_column(ForeignKey("rentals.id"), index=True)
    reference: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(20), default="booking")  # booking|installment|balance
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|success|failed
    provider: Mapped[str] = mapped_column(String(20), default="demo")   # paystack|demo
    channel: Mapped[str] = mapped_column(String(20), default="card")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lagos_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rental: Mapped[Rental] = relationship(back_populates="payments")


class TrackingPoint(Base):
    __tablename__ = "tracking_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    rental_id: Mapped[int] = mapped_column(ForeignKey("rentals.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=lagos_now, index=True)
    location: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float] = mapped_column(Float)
    over_limit: Mapped[bool] = mapped_column(Boolean, default=False)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    rental_id: Mapped[int] = mapped_column(ForeignKey("rentals.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # speeding|sos|low_fuel
    message: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lagos_now, index=True)
    rental: Mapped[Rental] = relationship()


class DamageClaim(Base):
    __tablename__ = "damage_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    rental_id: Mapped[int] = mapped_column(ForeignKey("rentals.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    damage_cost: Mapped[float] = mapped_column(Float)
    insurer_pays: Mapped[float] = mapped_column(Float)
    customer_pays: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|approved|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lagos_now)
    rental: Mapped[Rental] = relationship()


class Notification(Base):
    """A message to one customer: speeding warnings, licence reviews, notes from staff."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rental_id: Mapped[int | None] = mapped_column(ForeignKey("rentals.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="info")  # speeding|licence|staff|info
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lagos_now, index=True)


class DriverLicense(Base):
    """A customer's driver's licence, needed for self-drive bookings (learner's permits are refused)."""
    __tablename__ = "driver_licenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    number: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(40), default="")
    expires_on: Mapped[datetime] = mapped_column(DateTime)
    image_file: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted")  # submitted|verified|rejected
    review_note: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=lagos_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user: Mapped[User] = relationship()
