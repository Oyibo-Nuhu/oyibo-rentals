"""Known pickup/drop-off zones and route estimation.

Coordinates are approximate area centres. Road distances use a straight-line
(haversine) distance multiplied by a road factor, and drive time uses typical
Lagos traffic speeds. These are estimates for pricing, not navigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import asin, ceil, cos, radians, sin, sqrt

ROAD_FACTOR = 1.4              # roads are longer than a straight line
PEAK_SPEED_KMH = 18            # typical Lagos rush-hour speed
OFFPEAK_SPEED_KMH = 32
BIKE_SPEED_MULTIPLIER = 1.3    # bikes filter through traffic
BUFFER_HOURS = 0.5             # pickup, handover and parking time
MIN_ROUTE_HOURS = 2


@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    lat: float
    lng: float
    kind: str = "area"   # area | airport | hub


LAGOS_ZONES: dict[str, Zone] = {z.key: z for z in [
    Zone("lekki-phase-1", "Lekki Phase 1", 6.4474, 3.4723),
    Zone("ajah", "Ajah", 6.4698, 3.5852),
    Zone("victoria-island", "Victoria Island", 6.4281, 3.4219),
    Zone("ikoyi", "Ikoyi", 6.4549, 3.4346),
    Zone("surulere", "Surulere", 6.4969, 3.3481),
    Zone("yaba", "Yaba", 6.5095, 3.3711),
    Zone("ikeja", "Ikeja GRA", 6.5795, 3.3530),
    Zone("maryland", "Maryland", 6.5711, 3.3672),
    Zone("gbagada", "Gbagada", 6.5531, 3.3871),
    Zone("magodo", "Magodo", 6.6177, 3.3828),
    Zone("ikorodu", "Ikorodu", 6.6194, 3.5105),
    Zone("festac", "Festac Town", 6.4664, 3.2836),
    Zone("apapa", "Apapa", 6.4489, 3.3590),
    Zone("oshodi", "Oshodi", 6.5562, 3.3436),
    Zone("epe", "Epe", 6.5841, 3.9834),
    Zone("badagry", "Badagry", 6.4153, 2.8813),
    Zone("mmia", "Murtala Muhammed Airport", 6.5774, 3.3210, "airport"),
    Zone("lekki-ev-hub", "Lekki Solar EV Hub", 6.4400, 3.5300, "hub"),
    Zone("ikeja-ev-hub", "Ikeja Solar EV Hub", 6.6000, 3.3500, "hub"),
]}

# Approximate road distances from Lagos for cross-country estimates (km).
INTERSTATE_DESTINATIONS: dict[str, tuple[str, int]] = {
    "abeokuta": ("Abeokuta, Ogun", 80),
    "ibadan": ("Ibadan, Oyo", 130),
    "akure": ("Akure, Ondo", 310),
    "benin": ("Benin City, Edo", 320),
    "enugu": ("Enugu, Enugu", 560),
    "port-harcourt": ("Port Harcourt, Rivers", 610),
    "abuja": ("Abuja, FCT", 760),
    "kano": ("Kano, Kano", 1000),
}


def is_peak(moment: datetime) -> bool:
    """Weekday rush hours: 6–10am and 4–9pm."""
    if moment.weekday() >= 5:
        return False
    return 6 <= moment.hour < 10 or 16 <= moment.hour < 21


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def get_zone(key: str | None) -> Zone:
    """Reject empty or unknown locations."""
    if key is None or not str(key).strip():
        raise ValueError("Location cannot be empty.")
    zone = LAGOS_ZONES.get(str(key).strip().lower())
    if zone is None:
        raise ValueError(f"Unknown location: {key}.")
    return zone


@dataclass(frozen=True)
class RouteEstimate:
    pickup: Zone
    dropoff: Zone
    distance_km: float
    drive_hours: float
    booked_hours: int
    peak: bool


def estimate_route(pickup_key: str, dropoff_key: str, start: datetime, is_bike: bool = False) -> RouteEstimate:
    pickup = get_zone(pickup_key)
    dropoff = get_zone(dropoff_key)
    if pickup.key == dropoff.key:
        raise ValueError("Pickup and drop-off must be different locations.")

    distance = haversine_km(pickup.lat, pickup.lng, dropoff.lat, dropoff.lng) * ROAD_FACTOR
    peak = is_peak(start)
    speed = PEAK_SPEED_KMH if peak else OFFPEAK_SPEED_KMH
    if is_bike:
        speed *= BIKE_SPEED_MULTIPLIER
    drive_hours = distance / speed
    booked = max(MIN_ROUTE_HOURS, ceil(drive_hours + BUFFER_HOURS))
    return RouteEstimate(pickup, dropoff, round(distance, 1), round(drive_hours, 2), booked, peak)
