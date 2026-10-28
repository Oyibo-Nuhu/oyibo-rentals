"""Seeds the admin account, the fleet and (optionally) synthetic demo history.

Demo customers and their rentals are clearly flagged (users.is_demo) so you can
remove them before going live: set SEED_DEMO_DATA=false on a fresh database.
"""

from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select

from . import engine as eng
from .config import settings
from .locations import INTERSTATE_DESTINATIONS, LAGOS_ZONES
from .models import Alert, DamageClaim, DriverLicense, Payment, Rental, TrackingPoint, User, Vehicle, lagos_now
from .security import hash_password
from .services import booking_window, new_code

# (id, tier, brand, model, year, daily_rate, electric, seats, colour, home zone)
FLEET = [
    ("LX-001", "luxury", "Rolls-Royce", "Cullinan", 2024, 1_500_000, False, 5, "Arctic White", "ikoyi"),
    ("LX-002", "luxury", "Mercedes-Benz", "G 63 AMG", 2024, 650_000, False, 5, "Selenite Grey", "lekki-phase-1"),
    ("LX-003", "luxury", "Range Rover", "Autobiography", 2023, 550_000, False, 5, "Batumi Gold", "victoria-island"),
    ("LX-004", "luxury", "Lexus", "LX 600", 2023, 500_000, False, 7, "Sonic Quartz", "ikoyi"),
    ("LX-005", "luxury", "Mercedes-Benz", "S 580", 2023, 450_000, False, 5, "Diamond White", "victoria-island"),
    ("LX-006", "luxury", "Porsche", "Taycan", 2024, 480_000, True, 4, "Carrara White", "lekki-ev-hub"),
    ("EX-001", "executive", "Toyota", "Land Cruiser Prado", 2023, 180_000, False, 7, "Pearl White", "ikeja"),
    ("EX-002", "executive", "Lexus", "RX 350", 2022, 170_000, False, 5, "Eminent White", "lekki-phase-1"),
    ("EX-003", "executive", "Mercedes-Benz", "GLE 450", 2022, 200_000, False, 5, "Polar White", "victoria-island"),
    ("EX-004", "executive", "Toyota", "Highlander", 2022, 150_000, False, 7, "Celestial Silver", "ikeja"),
    ("EX-005", "executive", "Ford", "Explorer", 2021, 140_000, False, 7, "Carbonized Grey", "gbagada"),
    ("EX-006", "executive", "Hyundai", "Ioniq 5", 2024, 120_000, True, 5, "Cyber Grey", "lekki-ev-hub"),
    ("C001", "economy", "Toyota", "Camry", 2024, 65_000, False, 5, "Silver", "surulere"),
    ("C002", "economy", "Honda", "Accord", 2023, 60_000, False, 5, "Lunar Silver", "yaba"),
    ("EC-003", "economy", "Toyota", "Corolla", 2022, 45_000, False, 5, "White", "ikeja"),
    ("EC-004", "economy", "Honda", "Civic", 2022, 50_000, False, 5, "Platinum White", "maryland"),
    ("EC-005", "economy", "Hyundai", "Elantra", 2021, 45_000, False, 5, "Fluid Metal Grey", "festac"),
    ("EC-006", "economy", "Kia", "Rio", 2021, 35_000, False, 5, "Smoke Blue", "oshodi"),
    ("EC-007", "economy", "Innoson", "IVM Fox", 2023, 40_000, False, 5, "Green", "magodo"),
    ("EC-008", "economy", "BYD", "Atto 3", 2024, 85_000, True, 5, "Silver", "ikeja-ev-hub"),
    ("CM-001", "commercial", "Toyota", "Hiace", 2022, 120_000, False, 14, "Silver", "oshodi"),
    ("CM-002", "commercial", "Mercedes-Benz", "Sprinter", 2022, 150_000, False, 16, "White", "ikeja"),
    ("CM-003", "commercial", "Innoson", "IVM Caris", 2023, 100_000, False, 18, "Blue", "apapa"),
    ("CM-004", "commercial", "Ford", "Transit", 2021, 130_000, False, 12, "Frozen White", "yaba"),
    ("T001", "truck", "Mercedes-Benz", "Actros", 2022, 300_000, False, 2, "Silver", "apapa"),
    ("T002", "truck", "Volvo", "FH16", 2023, 320_000, False, 2, "White", "apapa"),
    ("TR-003", "truck", "MAN", "TGX", 2021, 280_000, False, 2, "White", "ikorodu"),
    ("TR-004", "truck", "Sinotruk", "HOWO", 2022, 250_000, False, 2, "Green", "ikorodu"),
    ("M001", "bike", "Honda", "CBR", 2024, 25_000, False, 2, "Black", "yaba"),
    ("M002", "bike", "Yamaha", "MT-07", 2023, 30_000, False, 2, "Icon Blue", "lekki-phase-1"),
    ("BK-003", "bike", "Bajaj", "CT100", 2023, 8_000, False, 2, "Black & Gold", "surulere"),
    ("BK-004", "bike", "TVS", "Apache RTR", 2023, 10_000, False, 2, "Matte Black", "ajah"),
    ("BK-005", "bike", "Spiro", "Ekon 450", 2024, 7_000, True, 2, "Electric Green", "ikeja-ev-hub"),
    # added in v2.1: more ways to move
    ("LX-007", "luxury", "Lamborghini", "Urus", 2024, 1_100_000, False, 4, "Verde Mantis Green", "ikoyi"),
    ("EX-007", "executive", "Toyota", "Sienna", 2022, 130_000, False, 8, "Blizzard Pearl White", "surulere"),
    ("EX-008", "executive", "Tesla", "Model Y", 2024, 160_000, True, 5, "Pearl White", "lekki-ev-hub"),
    ("EC-009", "economy", "Peugeot", "301", 2022, 38_000, False, 5, "White", "yaba"),
    ("CM-005", "commercial", "Toyota", "Hilux", 2023, 110_000, False, 5, "White", "apapa"),
    ("CM-006", "commercial", "Toyota", "Coaster", 2022, 200_000, False, 30, "White", "oshodi"),
    ("TR-005", "truck", "Isuzu", "NPR", 2021, 150_000, False, 3, "White", "ikeja"),
    ("TK-001", "tricycle", "Bajaj", "RE", 2023, 12_000, False, 3, "Green", "surulere"),
    ("TK-002", "tricycle", "TVS", "King", 2023, 11_000, False, 3, "Black", "ajah"),
    ("TK-003", "tricycle", "Piaggio", "Ape", 2023, 13_000, False, 3, "Sky Blue", "yaba"),
]

# Wikipedia article for each model; scripts/fetch_vehicle_photos.py uses its lead photo
# (freely licensed, hosted on Wikimedia Commons) and records the author and licence.
PHOTO_ARTICLES = {
    "LX-001": "Rolls-Royce Cullinan", "LX-002": "Mercedes-Benz G-Class", "LX-003": "Range Rover (L460)",
    "LX-004": "Lexus LX", "LX-005": "Mercedes-Benz S-Class (W223)", "LX-006": "Porsche Taycan",
    "LX-007": "Lamborghini Urus", "EX-001": "Toyota Land Cruiser Prado", "EX-002": "Lexus RX",
    "EX-003": "Mercedes-Benz GLE", "EX-004": "Toyota Highlander", "EX-005": "Ford Explorer",
    "EX-006": "Hyundai Ioniq 5", "EX-007": "Toyota Sienna", "EX-008": "Tesla Model Y",
    "C001": "Toyota Camry", "C002": "Honda Accord", "EC-003": "Toyota Corolla", "EC-004": "Honda Civic",
    "EC-005": "Hyundai Elantra", "EC-006": "Kia Rio", 
    "EC-008": "BYD Atto 3", "EC-009": "Peugeot 301", "CM-001": "Toyota HiAce", "CM-002": "Mercedes-Benz Sprinter",
     "CM-004": "Ford Transit", "CM-005": "Toyota Hilux",
    "CM-006": "Toyota Coaster", "T001": "Mercedes-Benz Actros", "T002": "Volvo FH", "TR-003": "MAN TGX",
    "TR-004": "Sinotruk HOWO", "TR-005": "Isuzu Elf", "M001": "Honda CBR600RR", "M002": "Yamaha MT-07",
    "BK-003": "Bajaj Boxer", "BK-004": "TVS Apache", "BK-005": "Spiro (company)", "TK-001": "Bajaj RE",
    "TK-002": "TVS King", "TK-003": "Piaggio Ape",
}

FIRST = ["Chidi", "Amaka", "Tunde", "Ngozi", "Emeka", "Funmi", "Ibrahim", "Aisha", "Seyi", "Kemi", "Obinna",
         "Zainab", "Femi", "Bisi", "Uche", "Halima", "Dayo", "Ifeoma", "Musa", "Tolu", "Kelechi", "Yetunde",
         "Segun", "Chiamaka", "Bola", "Nnamdi", "Hauwa", "Gbenga", "Adaeze", "Sani"]
LAST = ["Okafor", "Adeyemi", "Bello", "Eze", "Balogun", "Okonkwo", "Abubakar", "Ogunleye", "Nwosu", "Danjuma",
        "Adebayo", "Obi", "Lawal", "Chukwu", "Afolabi", "Usman", "Onyeka", "Ajayi", "Ibe", "Yusuf"]
ZONE_WEIGHTS = {"lekki-phase-1": 9, "victoria-island": 9, "ikeja": 8, "ikoyi": 6, "mmia": 7, "yaba": 5,
                "surulere": 5, "ajah": 4, "maryland": 3, "gbagada": 3, "magodo": 2, "festac": 3, "apapa": 3,
                "oshodi": 3, "ikorodu": 2, "epe": 1, "badagry": 1}
DAMAGES = ["Scratched rear bumper", "Cracked side mirror", "Dent on passenger door", "Windscreen chip from gravel",
           "Kerbed alloy wheel", "Broken tail light", "Pothole damage to front tyre", "Minor fender bender in traffic"]


def seed(db) -> None:
    if db.scalar(select(User).where(User.role == "admin")) is None:
        db.add(User(email=settings.admin_email, name="Fleet Admin", phone="08000000000",
                    password_hash=hash_password(settings.admin_password), role="admin", referral_code="OYADMIN"))
    existing = set(db.scalars(select(Vehicle.id)).all())
    for (vid, tier, brand, model, year, rate, ev, seats, colour, zone) in FLEET:
        if vid in existing:   # only add vehicles that are new, so admin edits are kept
            continue
        z = LAGOS_ZONES[zone]
        db.add(Vehicle(id=vid, tier=tier, brand=brand, model=model, year=year, daily_rate=rate, is_electric=ev,
                       seats=seats, color=colour, home_zone=zone, lat=z.lat, lng=z.lng,
                       plate=f"{random.choice(['LND', 'KJA', 'EKY', 'LSR', 'AAA'])}-{random.randint(100, 999)}"
                             f"{random.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{random.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}",
                       odometer_km=random.randint(3_000, 60_000)))
    db.commit()
    if settings.seed_demo_data and db.scalar(select(User).where(User.is_demo.is_(True))) is None:
        seed_demo_history(db)
    # the demo customer has a licence on file so self-drive bookings work straight away
    demo = db.scalar(select(User).where(User.email == "demo@oyibo.ng", User.is_demo.is_(True)))
    if demo and db.scalar(select(DriverLicense).where(DriverLicense.user_id == demo.id)) is None:
        db.add(DriverLicense(user_id=demo.id, number="LAG12345AA01", state="Lagos", status="verified",
                             expires_on=lagos_now() + timedelta(days=3 * 365), reviewed_at=lagos_now()))
        db.commit()


def seed_demo_history(db, n_customers: int = 90, n_rentals: int = 900, rng_seed: int = 2026) -> None:
    rng = random.Random(rng_seed)
    pw = hash_password("Demo1234!")
    customers = [User(email="demo@oyibo.ng", name="Oyibo Maya", phone="08039378598", password_hash=pw,
                      referral_code="OYDEMO1", is_demo=True)]
    used = set()
    while len(customers) < n_customers:
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name in used:
            continue
        used.add(name)
        customers.append(User(email=f"{name.lower().replace(' ', '.')}@example.ng", name=name,
                              phone=f"080{rng.randint(10_000_000, 99_999_999)}", password_hash=pw,
                              referral_code=f"OYD{len(customers):03d}", is_demo=True))
    db.add_all(customers)
    db.flush()
    # each customer has a habit: how often they rent, how hard they drive, and when they stopped
    habits = {c.id: {"weight": rng.paretovariate(1.3), "aggr": rng.betavariate(1.5, 6),
                     "churned_days": rng.choice([0, 0, 0, 60, 120, 200])} for c in customers}
    vehicles = db.scalars(select(Vehicle)).all()
    tier_weight = {"luxury": 1, "executive": 3, "economy": 6, "commercial": 2, "truck": 1.2, "bike": 3, "tricycle": 2}
    now = lagos_now()
    zones, zweights = zip(*ZONE_WEIGHTS.items())

    for i in range(n_rentals):
        customer = rng.choices(customers, weights=[habits[c.id]["weight"] for c in customers])[0]
        habit = habits[customer.id]
        days_ago = rng.betavariate(1.2, 1.6) * 365
        if habit["churned_days"] and days_ago < habit["churned_days"]:
            days_ago = habit["churned_days"] + rng.random() * 100
        day = now - timedelta(days=days_ago)
        if day.month != 12 and rng.random() < 0.12:   # "Detty December" demand spike
            december = day.replace(month=12, day=min(day.day, 28))
            if december < now:
                day = december
        hour = rng.choices(range(24), weights=[1, 1, 1, 1, 1, 2, 5, 9, 10, 8, 6, 6, 7, 6, 6, 7, 9, 10, 8, 6, 4, 3, 2, 1])[0]
        start = day.replace(hour=hour, minute=rng.choice([0, 15, 30, 45]), second=0, microsecond=0)
        if start > now - timedelta(hours=8):
            continue

        v = rng.choices(vehicles, weights=[tier_weight[x.tier] for x in vehicles])[0]
        ev = eng.build_vehicle(v.tier, v.id, v.brand, v.model, v.year, v.daily_rate, v.is_electric, v.seats)
        mode_weights = dict(zip(eng.MODES, [45, 18, 30, 7] if v.tier not in ("truck",) else [20, 10, 50, 20]))
        allowed = [m for m in eng.MODES if m in ev.ALLOWED_MODES]
        mode = rng.choices(allowed, weights=[mode_weights[m] for m in allowed])[0]
        kwargs = {"insurance_plan": rng.choices(["basic", "standard", "premium"], weights=[5, 4, 2])[0],
                  "with_driver": rng.random() < (0.5 if v.tier in ("luxury", "commercial", "truck") else 0.15)}
        if list(eng.INSURANCE_PLANS).index(kwargs["insurance_plan"]) < list(eng.INSURANCE_PLANS).index(ev.MIN_INSURANCE):
            kwargs["insurance_plan"] = ev.MIN_INSURANCE
        if mode == eng.ROUTE:
            a, b = rng.choices(zones, weights=zweights, k=2)
            if a == b:
                continue
            kwargs.update(pickup=a, dropoff=b)
        elif mode in (eng.FULL_DAY, eng.CROSS_COUNTRY):
            kwargs["days"] = rng.choices([1, 2, 3, 4, 5, 7, 10, 14, 30], weights=[30, 18, 14, 8, 8, 8, 5, 3, 1])[0]
            if mode == eng.CROSS_COUNTRY:
                kwargs["destination"] = rng.choice(list(INTERSTATE_DESTINATIONS))
        q = eng.quote_rental(ev, mode, start, **kwargs)
        end = booking_window(mode, start, q)

        if mode == eng.ROUTE:
            km = q.route["distance_km"] * rng.uniform(0.95, 1.4)
        elif mode == eng.CROSS_COUNTRY:
            km = INTERSTATE_DESTINATIONS[kwargs["destination"]][1] * 2 * rng.uniform(1.0, 1.3)
        else:
            km = rng.uniform(30, 160) * q.units if mode == eng.FULL_DAY else rng.uniform(25, 140)
        late_hours = 0 if rng.random() > 0.12 else rng.expovariate(1 / (3 if mode in (eng.ROUTE, eng.HALF_DAY) else 14))
        actual_end = end + timedelta(hours=late_hours)
        if actual_end > now:
            continue

        speeding = sum(1 for _ in range(max(1, int(km / 15))) if rng.random() < habit["aggr"] * 0.35)
        max_speed = rng.uniform(101, 135) if speeding else rng.uniform(55, 99)
        settle = eng.calculate_settlement(ev, q.as_dict(), end, actual_end, km,
                                          0 if kwargs["with_driver"] else speeding)
        r = Rental(code=new_code(), user_id=customer.id, vehicle_id=v.id, mode=mode, status="completed",
                   pickup_key=kwargs.get("pickup"), dropoff_key=kwargs.get("dropoff"),
                   destination=kwargs.get("destination"), start_at=start, end_at=end, actual_end_at=actual_end,
                   with_driver=kwargs["with_driver"], insurance_plan=kwargs["insurance_plan"], quote=q.as_dict(),
                   total_due=round(q.total_due, 2), settlement=settle, final_cost=settle["final_cost"],
                   distance_km=round(km, 1), speeding_events=speeding, max_speed=round(max_speed, 1),
                   rating=rng.choices([5, 4, 3, 2, 1], weights=[50, 30, 12, 5, 3])[0] if rng.random() < 0.7 else None,
                   created_at=(start - timedelta(hours=rng.uniform(0.5, 72))).replace(microsecond=0))
        db.add(r)
        db.flush()
        db.add(Payment(rental_id=r.id, reference=new_code("PAY"), amount=r.total_due, status="success",
                       provider="demo", channel=rng.choices(["card", "bank_transfer", "ussd"], weights=[6, 3, 1])[0],
                       created_at=r.created_at, paid_at=r.created_at))
        claim_p = 0.03 + habit["aggr"] * 0.12 + (0.04 if v.tier in ("truck", "bike") else 0)
        if rng.random() < claim_p:
            cost = round(rng.lognormvariate(12.2, 0.9), -3)
            payout = eng.calculate_claim_payout(r.insurance_plan, cost)
            db.add(DamageClaim(rental_id=r.id, description=rng.choice(DAMAGES), damage_cost=cost,
                               insurer_pays=payout["insurer_pays"], customer_pays=payout["customer_pays"],
                               status=rng.choices(["approved", "rejected", "open"], weights=[7, 1, 2])[0],
                               created_at=actual_end))
        customer.loyalty_points += int(r.total_due // 1000)

    # A few rentals on the road right now, so the live map has something to show.
    live = [("EX-002", "lekki-phase-1", "surulere"), ("C001", "ikeja", "victoria-island"),
            ("M002", "yaba", "ajah"), ("CM-001", None, None), ("LX-006", None, None), ("T002", None, None)]
    for idx, (vid, a, b) in enumerate(live):
        v = db.get(Vehicle, vid)
        ev = eng.build_vehicle(v.tier, v.id, v.brand, v.model, v.year, v.daily_rate, v.is_electric, v.seats)
        start = now - timedelta(minutes=20 + idx * 7)
        plan = ev.MIN_INSURANCE
        if a:
            q = eng.quote_rental(ev, eng.ROUTE, start, pickup=a, dropoff=b, insurance_plan=plan)
            mode = eng.ROUTE
        else:
            q = eng.quote_rental(ev, eng.FULL_DAY, start, days=1, insurance_plan=plan)
            mode = eng.FULL_DAY
        owner = customers[0] if idx == 0 else rng.choice(customers[1:])
        r = Rental(code=new_code(), user_id=owner.id, vehicle_id=v.id, mode=mode, status="active", pickup_key=a,
                   dropoff_key=b, start_at=start, end_at=booking_window(mode, start, q), insurance_plan=plan,
                   quote=q.as_dict(), total_due=round(q.total_due, 2), created_at=start - timedelta(minutes=10))
        v.status = "rented"
        start_zone = LAGOS_ZONES[a] if a else LAGOS_ZONES[v.home_zone]
        v.lat, v.lng = start_zone.lat, start_zone.lng
        db.add(r)
        db.flush()
        db.add(Payment(rental_id=r.id, reference=new_code("PAY"), amount=r.total_due, status="success",
                       provider="demo", channel="card", created_at=r.created_at, paid_at=r.created_at))
        db.add(TrackingPoint(rental_id=r.id, ts=start, location=f"Near {start_zone.name}", lat=v.lat, lng=v.lng,
                             speed_kmh=0, over_limit=False))
    first_active = db.scalar(select(Rental).where(Rental.status == "active"))
    if first_active:
        db.add(Alert(rental_id=first_active.id, kind="speeding", created_at=now - timedelta(minutes=3),
                     message="Speed warning: 112.0 km/h exceeds the 100 km/h limit near Third Mainland Bridge."))
    db.commit()
