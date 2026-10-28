"""Simulated GPS feed for active rentals.

Real vehicles would post to POST /api/tracking/{code}/ping from a GPS device or
the driver's phone. Until that hardware exists, this simulator moves active
rentals around Lagos so the live map, speed alerts and analytics have data.
Turn it off with RUN_TRACKING_SIMULATOR=false.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta

from sqlalchemy import select

from .database import SessionLocal
from .locations import LAGOS_ZONES, haversine_km, is_peak
from .models import Rental, lagos_now
from .services import record_tracking, start_due_rentals

log = logging.getLogger("simulator")
TICK_SECONDS = 4
WANDER_SPEEDUP = 3          # makes free-roaming vehicles visibly move on the map
SPEEDING_CHANCE = 0.06
_targets: dict[int, str] = {}


def nearest_zone_name(lat: float, lng: float) -> str:
    zone = min(LAGOS_ZONES.values(), key=lambda z: haversine_km(lat, lng, z.lat, z.lng))
    return f"Near {zone.name}"


def simulated_speed(rental: Rental, now) -> float:
    if random.random() < SPEEDING_CHANCE:
        return round(random.uniform(101, 128), 1)
    base = 22 if is_peak(now) else 45
    if rental.vehicle.tier == "truck":
        base *= 0.8
    return round(max(0.0, random.gauss(base, 12)), 1)


def step_rental(db, rental: Rental, now) -> None:
    v = rental.vehicle
    home = LAGOS_ZONES.get(v.home_zone) or LAGOS_ZONES["ikeja"]
    lat, lng = (v.lat, v.lng) if v.lat is not None else (home.lat, home.lng)
    speed = simulated_speed(rental, now)

    if rental.pickup_key and rental.dropoff_key:
        a, b = LAGOS_ZONES[rental.pickup_key], LAGOS_ZONES[rental.dropoff_key]
        total = (rental.end_at - rental.start_at).total_seconds()
        frac = min(1.0, max(0.0, (now - rental.start_at).total_seconds() / max(total * 0.8, 1)))
        new_lat = a.lat + (b.lat - a.lat) * frac + random.uniform(-0.0015, 0.0015)
        new_lng = a.lng + (b.lng - a.lng) * frac + random.uniform(-0.0015, 0.0015)
        if frac >= 1.0:
            speed = round(random.uniform(0, 8), 1)
    else:
        target_key = _targets.get(rental.id)
        if target_key is None or haversine_km(lat, lng, LAGOS_ZONES[target_key].lat, LAGOS_ZONES[target_key].lng) < 0.4:
            choices = [z for z in LAGOS_ZONES.values() if z.kind != "hub" and 1 < haversine_km(lat, lng, z.lat, z.lng) < 18]
            target_key = random.choice(choices or list(LAGOS_ZONES.values())).key
            _targets[rental.id] = target_key
        t = LAGOS_ZONES[target_key]
        dist = haversine_km(lat, lng, t.lat, t.lng) or 1e-6
        step = min(dist, speed * TICK_SECONDS / 3600 * WANDER_SPEEDUP)
        new_lat = lat + (t.lat - lat) * step / dist
        new_lng = lng + (t.lng - lng) * step / dist

    record_tracking(db, rental, nearest_zone_name(new_lat, new_lng), new_lat, new_lng, speed, now, simulated=True)


def tick() -> None:
    with SessionLocal() as db:
        start_due_rentals(db)
        now = lagos_now()
        active = db.scalars(select(Rental).where(Rental.status == "active")).all()
        for rental in active:
            if rental.user.is_demo and rental.end_at < now + timedelta(hours=1):
                rental.end_at = now + timedelta(days=1)   # keep the demo map alive
            try:
                step_rental(db, rental, now)
            except Exception as error:   # one bad rental should not stop the feed
                log.warning("simulator skipped %s: %s", rental.code, error)
        db.commit()


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:
            log.exception("simulator tick failed")
        await asyncio.sleep(TICK_SECONDS)
