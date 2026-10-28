"""Rental engine — grown from Oyibo Nuhu Ojochogwu's OOP Vehicle Rental System.

The original classes (Vehicle, Car, Motorcycle, Truck, Rental) keep their
roles and rules:
  * encapsulated daily rate and availability,
  * polymorphic calculate_rental_cost(),
  * multi-day discounts (5% / 10% / 15%),
  * first 100 km free, then a per-km charge by vehicle type,
  * late return charge of 20% of the daily rate per late day,
  * a refundable security deposit,
  * tracking that rejects empty locations and flags speed above 100 km/h.

New in this version: fleet tiers (luxury to bikes), rental modes (route,
half day, full day, cross country), damage insurance, driver add-on,
peak-hour pricing, EV discount and VAT.

This module has no database or web code, so it can be unit tested on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from math import ceil, isfinite

from .locations import INTERSTATE_DESTINATIONS, estimate_route, is_peak

VAT_RATE = 0.075
SPEED_LIMIT_KMH = 100

# Rental modes
ROUTE, HALF_DAY, FULL_DAY, CROSS_COUNTRY = "route", "half_day", "full_day", "cross_country"
MODES = (ROUTE, HALF_DAY, FULL_DAY, CROSS_COUNTRY)

ROUTE_HOURLY_FACTOR = 0.10      # hourly route rate = 10% of the daily rate
HALF_DAY_FACTOR = 0.60          # 6 hours, any location
HALF_DAY_HOURS = 6
CROSS_COUNTRY_FACTOR = 1.35     # interstate wear, risk and recovery cost
INTERSTATE_FEE = 25_000         # documents pack and permits handling
PEAK_SURCHARGE = 0.20
SPEEDING_FREE_STRIKES = 3       # warnings before the speeding charge starts
SPEEDING_FEE = 5_000            # per speeding incident after the free strikes
EV_DISCOUNT = 0.10

DRIVER_RATES = {ROUTE: 3_000, HALF_DAY: 12_000, FULL_DAY: 20_000, CROSS_COUNTRY: 30_000}

INSURANCE_PLANS = {
    "basic":    {"label": "Basic",    "rate": 0.06, "cover_cap": 1_000_000,  "excess": 150_000},
    "standard": {"label": "Standard", "rate": 0.10, "cover_cap": 5_000_000,  "excess": 50_000},
    "premium":  {"label": "Premium",  "rate": 0.15, "cover_cap": 25_000_000, "excess": 0},
}


# VEHICLE CLASS
# -------------

class Vehicle:
    TIER = "vehicle"
    TIER_LABEL = "Vehicle"
    DEFAULT_DAILY_RATE = 10_000
    MILEAGE_RATE = 100            # naira per km after the free 100 km
    SECURITY_DEPOSIT = 50_000
    SPEED_LIMIT_KMH = SPEED_LIMIT_KMH
    MIN_INSURANCE = "basic"
    ALLOWED_MODES = MODES         # subclasses can restrict this (kekes stay in town)

    def __init__(self, vehicle_id, brand, model, year, daily_rate=None, is_electric=False, seats=4):
        if not str(brand).strip() or not str(model).strip():
            raise ValueError("Brand and model cannot be empty.")
        self.vehicle_id = vehicle_id
        self.brand = brand
        self.model = model
        self.year = year
        self.is_electric = is_electric
        self.seats = seats
        self.__daily_rate = daily_rate if daily_rate is not None else self.DEFAULT_DAILY_RATE
        if self.__daily_rate <= 0:
            raise ValueError("Daily rate must be greater than zero.")
        self.__is_available = True

    # Encapsulation: the daily rate is set at creation and read through a getter.
    def get_daily_rate(self):
        return self.__daily_rate

    def get_hourly_route_rate(self):
        return self.__daily_rate * ROUTE_HOURLY_FACTOR

    def is_available(self):
        return self.__is_available

    def set_available(self, available: bool):
        self.__is_available = bool(available)

    def rent_vehicle(self):
        if not self.__is_available:
            raise ValueError("Vehicle is already rented.")
        self.__is_available = False
        return "Vehicle status changed to Rented."

    def return_vehicle(self):
        if self.__is_available:
            raise ValueError("Vehicle is already available.")
        self.__is_available = True
        return "Vehicle status changed to Available."

    def get_speed_limit(self):
        return self.SPEED_LIMIT_KMH

    # Polymorphic method, as in the original project.
    def calculate_rental_cost(self, days):
        return self.__daily_rate * days

    def vehicle_type(self):
        return self.TIER_LABEL

    def is_bike(self):
        return False

    def get_details(self):
        status = "Available" if self.__is_available else "Rented"
        return (f"ID: {self.vehicle_id} | Type: {self.vehicle_type()} | Brand: {self.brand} | "
                f"Model: {self.model} | Year: {self.year} | "
                f"Daily Rate: ₦{self.get_daily_rate():,.2f} | Status: {status}")


# CAR FAMILY
# ----------

class Car(Vehicle):
    TIER = "economy"
    TIER_LABEL = "Economy Car"
    DEFAULT_DAILY_RATE = 45_000


class ExecutiveCar(Car):
    TIER = "executive"
    TIER_LABEL = "Executive & SUV"
    DEFAULT_DAILY_RATE = 150_000
    MILEAGE_RATE = 150
    SECURITY_DEPOSIT = 150_000


class LuxuryCar(Car):
    TIER = "luxury"
    TIER_LABEL = "Luxury"
    DEFAULT_DAILY_RATE = 450_000
    MILEAGE_RATE = 250
    SECURITY_DEPOSIT = 300_000
    MIN_INSURANCE = "standard"


class CommercialVehicle(Vehicle):
    TIER = "commercial"
    TIER_LABEL = "Commercial (Bus, Van & Pickup)"
    DEFAULT_DAILY_RATE = 120_000
    MILEAGE_RATE = 150
    SECURITY_DEPOSIT = 100_000


# MOTORCYCLE CLASS
# ----------------

class Motorcycle(Vehicle):
    TIER = "bike"
    TIER_LABEL = "Bike"
    DEFAULT_DAILY_RATE = 15_000
    MILEAGE_RATE = 50
    SECURITY_DEPOSIT = 20_000

    def is_bike(self):
        return True


# TRICYCLE (KEKE) CLASS
# ---------------------

class Tricycle(Motorcycle):
    """Keke NAPEP-style tricycle. Inherits bike routing (it weaves through traffic)
    but is restricted to in-state trips, like kekes on Lagos highways."""
    TIER = "tricycle"
    TIER_LABEL = "Keke (Tricycle)"
    DEFAULT_DAILY_RATE = 12_000
    MILEAGE_RATE = 60
    SECURITY_DEPOSIT = 30_000
    ALLOWED_MODES = (ROUTE, HALF_DAY, FULL_DAY)


# TRUCK CLASS
# -----------

class Truck(Vehicle):
    TIER = "truck"
    TIER_LABEL = "Truck"
    DEFAULT_DAILY_RATE = 250_000
    MILEAGE_RATE = 200
    SECURITY_DEPOSIT = 150_000


TIER_CLASSES = {cls.TIER: cls for cls in
                (LuxuryCar, ExecutiveCar, Car, CommercialVehicle, Truck, Motorcycle, Tricycle)}
TIER_ORDER = ["luxury", "executive", "economy", "commercial", "truck", "bike", "tricycle"]


def build_vehicle(tier, vehicle_id, brand, model, year, daily_rate=None, is_electric=False, seats=4, available=True):
    cls = TIER_CLASSES.get(tier)
    if cls is None:
        raise ValueError(f"Unknown vehicle tier: {tier}.")
    vehicle = cls(vehicle_id, brand, model, year, daily_rate, is_electric, seats)
    vehicle.set_available(available)
    return vehicle


# TRACKING
# --------

def validate_tracking_update(vehicle: Vehicle, location, speed_kmh):
    """Same checks as the original Rental.update_tracking(); returns the reading."""
    if not isinstance(location, str) or not location.strip():
        raise ValueError("Location cannot be empty.")
    if isinstance(speed_kmh, bool) or not isinstance(speed_kmh, (int, float)) \
            or not isfinite(speed_kmh) or speed_kmh < 0:
        raise ValueError("Speed must be a finite, non-negative number.")
    return {
        "location": location.strip(),
        "speed_kmh": float(speed_kmh),
        "over_speed_limit": speed_kmh > vehicle.get_speed_limit(),
    }


# QUOTE
# -----

@dataclass
class Quote:
    mode: str
    vehicle_id: str
    units: float                  # hours for route/half day, days otherwise
    unit_label: str
    base_cost: float
    discount: float = 0.0
    peak_surcharge: float = 0.0
    ev_discount: float = 0.0
    driver_fee: float = 0.0
    insurance_plan: str = "basic"
    insurance_fee: float = 0.0
    interstate_fee: float = 0.0
    vat: float = 0.0
    security_deposit: float = 0.0
    total_due: float = 0.0
    included_km: float = 100.0
    route: dict | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def subtotal(self):
        return (self.base_cost - self.discount + self.peak_surcharge - self.ev_discount
                + self.driver_fee + self.insurance_fee + self.interstate_fee)

    def as_dict(self):
        data = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.__dict__.items()}
        data["subtotal"] = round(self.subtotal, 2)
        return data


def multi_day_discount(base_cost, days):
    """Original discount rules: 7–13 days 5%, 14–29 days 10%, 30+ days 15%."""
    if days >= 30:
        return base_cost * 0.15
    if days >= 14:
        return base_cost * 0.10
    if days >= 7:
        return base_cost * 0.05
    return 0


def quote_rental(vehicle: Vehicle, mode: str, start: datetime, *, days: int = 1, pickup: str | None = None,
                 dropoff: str | None = None, destination: str | None = None,
                 insurance_plan: str = "basic", with_driver: bool = False) -> Quote:
    if mode not in MODES:
        raise ValueError(f"Unknown rental mode: {mode}.")
    if insurance_plan not in INSURANCE_PLANS:
        raise ValueError("Unknown insurance plan.")
    if mode not in vehicle.ALLOWED_MODES:
        raise ValueError(f"{vehicle.TIER_LABEL} vehicles can't be booked for {mode.replace('_', ' ')} trips.")
    order = list(INSURANCE_PLANS)
    if order.index(insurance_plan) < order.index(vehicle.MIN_INSURANCE):
        raise ValueError(f"{vehicle.TIER_LABEL} vehicles need at least "
                         f"{INSURANCE_PLANS[vehicle.MIN_INSURANCE]['label']} insurance.")

    route = None
    if mode == ROUTE:
        estimate = estimate_route(pickup, dropoff, start, vehicle.is_bike())
        units, unit_label = estimate.booked_hours, "hours"
        base = vehicle.get_hourly_route_rate() * units
        peak = estimate.peak
        included_km = max(20.0, round(estimate.distance_km * 1.25, 1))
        route = {
            "pickup": estimate.pickup.name, "pickup_key": estimate.pickup.key,
            "dropoff": estimate.dropoff.name, "dropoff_key": estimate.dropoff.key,
            "distance_km": estimate.distance_km, "drive_hours": estimate.drive_hours,
            "pickup_coords": [estimate.pickup.lat, estimate.pickup.lng],
            "dropoff_coords": [estimate.dropoff.lat, estimate.dropoff.lng],
        }
    elif mode == HALF_DAY:
        units, unit_label = HALF_DAY_HOURS, "hours"
        base = vehicle.get_daily_rate() * HALF_DAY_FACTOR
        peak = is_peak(start)
        included_km = 100.0
    else:
        if not isinstance(days, int) or days <= 0:
            raise ValueError("Rental period must be greater than zero.")
        if days > 90:
            raise ValueError("Rental period cannot exceed 90 days.")
        units, unit_label = days, "days"
        base = vehicle.calculate_rental_cost(days)
        if mode == CROSS_COUNTRY:
            base *= CROSS_COUNTRY_FACTOR
        peak = False
        included_km = 100.0 * days if mode == FULL_DAY else 250.0 * days

    q = Quote(mode=mode, vehicle_id=vehicle.vehicle_id, units=units, unit_label=unit_label,
              base_cost=float(base), insurance_plan=insurance_plan, included_km=included_km, route=route)

    if mode in (FULL_DAY, CROSS_COUNTRY):
        q.discount = float(multi_day_discount(base, days))
        if q.discount:
            q.notes.append("Multi-day discount applied.")
    if peak:
        q.peak_surcharge = base * PEAK_SURCHARGE
        q.notes.append("Lagos rush-hour pricing (+20%).")
    if vehicle.is_electric:
        q.ev_discount = base * EV_DISCOUNT
        q.notes.append("Green ride: 10% off for electric vehicles.")
    if with_driver:
        rate = DRIVER_RATES[mode]
        q.driver_fee = float(rate * (units if mode in (ROUTE, FULL_DAY, CROSS_COUNTRY) else 1))
    if mode == CROSS_COUNTRY:
        q.interstate_fee = float(INTERSTATE_FEE)
        if destination:
            dest = INTERSTATE_DESTINATIONS.get(destination)
            if dest is None:
                raise ValueError("Unknown interstate destination.")
            q.route = {"destination": dest[0], "distance_km": dest[1]}
            q.notes.append(f"Lagos to {dest[0]} is about {dest[1]} km by road.")

    q.insurance_fee = (base - q.discount) * INSURANCE_PLANS[insurance_plan]["rate"]
    q.vat = q.subtotal * VAT_RATE
    q.security_deposit = float(vehicle.SECURITY_DEPOSIT)
    q.total_due = q.subtotal + q.vat + q.security_deposit
    return q


# SETTLEMENT ON RETURN
# --------------------

GRACE_MINUTES = 15


def speeding_charge(incidents: int) -> float:
    """More than SPEEDING_FREE_STRIKES incidents in one rental: SPEEDING_FEE for each one after that."""
    return max(0, int(incidents) - SPEEDING_FREE_STRIKES) * SPEEDING_FEE


def calculate_settlement(vehicle: Vehicle, quote: dict, booked_end: datetime, actual_end: datetime,
                         actual_km: float, speeding_incidents: int = 0) -> dict:
    """Final charges when a rental ends, following the original rules.

    * Mileage beyond the included allowance is charged per km by vehicle type.
    * Day rentals: late charge is 20% of the daily rate per late day started.
    * Hourly rentals: each late hour started costs 120% of the hourly rate.
    * More than 3 speeding incidents: ₦5,000 for each one after the third (no VAT: it is a penalty).
    * The security deposit is refunded minus any extra charges.
    """
    if actual_km < 0:
        raise ValueError("Mileage cannot be negative.")
    extra_km = max(0.0, actual_km - quote["included_km"])
    mileage_charge = extra_km * vehicle.MILEAGE_RATE

    late_seconds = (actual_end - booked_end).total_seconds() - GRACE_MINUTES * 60
    late_charge, late_units = 0.0, 0
    if late_seconds > 0:
        if quote["mode"] in (ROUTE, HALF_DAY):
            late_units = ceil(late_seconds / 3600)
            late_charge = late_units * vehicle.get_hourly_route_rate() * 1.2
        else:
            late_units = ceil(late_seconds / 86400)
            late_charge = vehicle.get_daily_rate() * 0.20 * late_units

    speeding = speeding_charge(speeding_incidents)
    extras = (mileage_charge + late_charge) * (1 + VAT_RATE) + speeding
    deposit = quote["security_deposit"]
    return {
        "actual_km": round(actual_km, 1),
        "extra_km": round(extra_km, 1),
        "mileage_charge": round(mileage_charge, 2),
        "late_units": late_units,
        "late_unit_label": "hours" if quote["mode"] in (ROUTE, HALF_DAY) else "days",
        "late_charge": round(late_charge, 2),
        "speeding_incidents": int(speeding_incidents),
        "speeding_charge": round(speeding, 2),
        "extras_with_vat": round(extras, 2),
        "deposit_refund": round(max(0.0, deposit - extras), 2),
        "balance_due": round(max(0.0, extras - deposit), 2),
        "final_cost": round(quote["total_due"] - deposit + extras, 2),
    }


def calculate_claim_payout(plan: str, damage_cost: float) -> dict:
    if damage_cost <= 0:
        raise ValueError("Damage cost must be greater than zero.")
    p = INSURANCE_PLANS[plan]
    covered = min(max(0.0, damage_cost - p["excess"]), p["cover_cap"])
    return {"plan": plan, "damage_cost": damage_cost, "excess": p["excess"],
            "insurer_pays": round(covered, 2), "customer_pays": round(damage_cost - covered, 2)}


# DRIVER'S LICENCE
# ----------------

LICENCE_KINDS = {"full": "Full driver's licence", "learner": "Learner's permit"}


def validate_driver_licence(kind: str, number: str, expires_on: date, today: date) -> str:
    """Self-drive needs a full licence that hasn't expired. Returns the cleaned licence number."""
    if kind == "learner":
        raise ValueError("Learner's permits aren't accepted for self-drive. Add a driver to your booking instead.")
    if kind not in LICENCE_KINDS:
        raise ValueError("Choose the type of licence.")
    clean = re.sub(r"[\s-]", "", number or "").upper()
    if not re.fullmatch(r"[A-Z0-9]{8,20}", clean):
        raise ValueError("Enter the licence number as printed on the card (8 to 20 letters and numbers).")
    if expires_on <= today:
        raise ValueError("This licence has expired. Renew it, or add a driver to your booking.")
    return clean
