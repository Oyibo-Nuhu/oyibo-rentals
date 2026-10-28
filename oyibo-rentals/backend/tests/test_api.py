"""End-to-end through the HTTP API: sign up, book, pay, track, SOS, damage, return, admin."""
from tests.conftest import auth


def book(client, headers, **body):
    r = client.post("/api/rentals", headers=headers, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    paid = client.post(f"/api/payments/{data['payment']['reference']}/demo-confirm", headers=headers, json={"channel": "card"})
    assert paid.status_code == 200 and paid.json()["status"] == "success", paid.text
    return paid.json()["rental"]


def test_meta_lists_all_vehicle_classes(client):
    tiers = [t["key"] for t in client.get("/api/meta").json()["tiers"]]
    assert tiers == ["luxury", "executive", "economy", "commercial", "truck", "bike", "tricycle"]


def test_fleet_search_like_the_original(client):
    rows = client.get("/api/fleet", params={"q": "keke"}).json()
    assert rows and all(r["tier"] == "tricycle" for r in rows)
    assert all("cross_country" not in r["allowed_modes"] for r in rows)


def test_register_validation_and_duplicates(client, customer):
    bad = client.post("/api/auth/register", json={"name": "X", "email": "nope", "phone": "1", "password": "short"})
    assert bad.status_code == 422
    dup = client.post("/api/auth/register", json={"name": "Nuhu Oyibo", "email": "NUHU@test.ng",
                                                  "phone": "08039378598", "password": "Lagos#Drive2026"})
    assert dup.status_code == 409
    wrong = client.post("/api/auth/login", json={"email": "nuhu@test.ng", "password": "wrong-password"})
    assert wrong.status_code == 401


def test_quote_needs_locations_for_route(client):
    r = client.post("/api/quote", json={"vehicle_id": "EC-003", "mode": "route", "pickup": "", "dropoff": "surulere"})
    assert r.status_code == 422


def test_full_trip_lifecycle(client, customer, admin):
    rental = book(client, customer, vehicle_id="EC-003", mode="route", pickup="lekki-phase-1", dropoff="surulere")
    code = rental["code"]
    assert rental["status"] == "active"
    # the same car can't be double-booked
    clash = client.post("/api/rentals", headers=customer, json={"vehicle_id": "EC-003", "mode": "half_day"})
    assert clash.status_code == 409

    ok = client.post(f"/api/tracking/{code}/ping", headers=customer,
                     json={"location": "Lekki-Epe Expressway", "lat": 6.44, "lng": 3.47, "speed_kmh": 72})
    assert ok.status_code == 200
    fast = client.post(f"/api/tracking/{code}/ping", headers=customer,
                       json={"location": "Third Mainland Bridge", "lat": 6.50, "lng": 3.40, "speed_kmh": 131})
    assert fast.status_code == 200 and "exceeds" in fast.text.lower()
    empty = client.post(f"/api/tracking/{code}/ping", headers=customer,
                        json={"location": "  ", "lat": 6.5, "lng": 3.4, "speed_kmh": 40})
    assert empty.status_code in (400, 422)

    alerts = client.get("/api/tracking/alerts", headers=admin).json()
    assert any(a["rental"] == code and a["kind"] == "speeding" for a in alerts)
    assert client.post(f"/api/rentals/{code}/sos", headers=customer, json={"message": "Flat tyre"}).status_code == 200

    claim = client.post(f"/api/rentals/{code}/claims", headers=customer,
                        json={"description": "Pothole damage to front tyre", "damage_cost": 80_000})
    assert claim.status_code == 200 and claim.json()["insurer_pays"] + claim.json()["customer_pays"] == 80_000

    ended = client.post(f"/api/rentals/{code}/end", headers=customer)
    assert ended.status_code == 200 and ended.json()["rental"]["status"] == "completed"
    assert client.post(f"/api/rentals/{code}/rate", headers=customer, json={"rating": 5}).status_code == 200


def test_keke_cross_country_blocked_by_api(client, customer):
    r = client.post("/api/rentals", headers=customer, json={"vehicle_id": "TK-001", "mode": "cross_country",
                                                            "days": 2, "destination": "ibadan"})
    assert r.status_code == 422


def test_pay_small_small_needs_seven_days(client, customer):
    r = client.post("/api/rentals", headers=customer, json={"vehicle_id": "EX-004", "mode": "full_day", "days": 3,
                                                            "payment_plan": "installments"})
    assert r.status_code == 422
    book(client, customer, vehicle_id="EX-004", mode="full_day", days=7, payment_plan="installments")


def test_customers_cannot_see_admin(client, customer):
    assert client.get("/api/admin/analytics", headers=customer).status_code == 403
    assert client.get("/api/admin/users", headers=customer).status_code == 403


def test_analytics_and_filters(client, customer, admin):
    book(client, customer, vehicle_id="TK-002", mode="route", pickup="ajah", dropoff="lekki-phase-1")
    full = client.get("/api/admin/analytics", headers=admin).json()
    assert full["kpis"]["rental_count"] >= 3
    for key in ("insights", "race", "calendar", "zone_map", "podium", "simulator_base", "spark", "options"):
        assert key in full
    keke = client.get("/api/admin/analytics", headers=admin, params={"tiers": "tricycle"}).json()
    assert keke["kpis"]["rental_count"] >= 1 and {t["tier"] for t in keke["by_tier_key"]} == {"tricycle"}
    none = client.get("/api/admin/analytics", headers=admin, params={"start": "2000-01-01", "end": "2000-01-02"}).json()
    assert none.get("no_match") is True
    bad = client.get("/api/admin/analytics", headers=admin, params={"start": "2026-02-01", "end": "2026-01-01"})
    assert bad.status_code == 422
    csv = client.get("/api/admin/analytics/export.csv", headers=admin)
    assert csv.status_code == 200 and "rental_id" in csv.text


def test_admin_photo_upload(client, admin):
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (1200, 800), (255, 46, 99)).save(buf, "PNG")
    r = client.post("/api/admin/fleet/TK-003/photo", headers=admin, files={"file": ("keke.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200 and r.json()["photo"].startswith("/static/img/fleet/TK-003.jpg")
    junk = client.post("/api/admin/fleet/TK-003/photo", headers=admin, files={"file": ("x.png", b"not an image", "image/png")})
    assert junk.status_code == 422


def test_admin_can_take_a_vehicle_offline_and_back(client, customer, admin):
    off = client.post("/api/admin/fleet/EC-005/status", headers=admin, json={"status": "unavailable"})
    assert off.status_code == 200 and off.json()["status"] == "unavailable"
    blocked = client.post("/api/quote", json={"vehicle_id": "EC-005", "mode": "half_day"})
    assert blocked.status_code == 409 and "available" in blocked.json()["detail"]
    shop = client.post("/api/admin/fleet/EC-005/status", headers=admin, json={"status": "maintenance"})
    assert shop.json()["status"] == "maintenance"
    assert client.post("/api/quote", json={"vehicle_id": "EC-005", "mode": "half_day"}).status_code == 409
    back = client.post("/api/admin/fleet/EC-005/status", headers=admin, json={"status": "available"})
    assert back.json()["status"] == "available"
    assert client.post("/api/quote", json={"vehicle_id": "EC-005", "mode": "half_day"}).status_code == 200
    assert client.post("/api/admin/fleet/EC-005/status", headers=admin, json={"status": "sold"}).status_code == 422
    assert client.post("/api/admin/fleet/EC-005/status", headers=customer, json={"status": "unavailable"}).status_code == 403


def test_admin_adds_a_new_slot_with_photo_and_new_price(client, admin):
    from io import BytesIO
    from PIL import Image
    r = client.post("/api/admin/fleet", headers=admin, json={"id": "ex-099", "tier": "executive", "brand": "Toyota",
                                                              "model": "Venza", "year": 2024, "seats": 5, "home_zone": "ikeja"})
    assert r.status_code == 200 and r.json()["vehicle"]["id"] == "EX-099"
    assert client.post("/api/admin/fleet", headers=admin, json={"id": "EX-099", "tier": "executive", "brand": "X",
                                                                 "model": "Y", "year": 2024}).status_code == 409
    buf = BytesIO(); Image.new("RGB", (800, 500), (40, 40, 60)).save(buf, "JPEG")
    up = client.post("/api/admin/fleet/EX-099/photo", headers=admin, files={"file": ("venza.jpg", buf.getvalue(), "image/jpeg")})
    assert up.status_code == 200 and up.json()["photo"]
    rate = client.post("/api/admin/fleet/EX-099/rate", headers=admin, json={"daily_rate": 175000})
    assert rate.status_code == 200 and rate.json()["daily_rate"] == 175000
    assert client.post("/api/admin/fleet/EX-099/rate", headers=admin, json={"daily_rate": 0}).status_code == 422
    listed = {v["id"]: v for v in client.get("/api/fleet").json()}
    assert listed["EX-099"]["photo"] and listed["EX-099"]["daily_rate"] == 175000


def test_self_drive_needs_a_licence_but_a_driver_does_not(client):
    from tests.conftest import submit_licence
    r = client.post("/api/auth/register", json={"name": "Ada Okafor", "email": "ada@test.ng", "phone": "08123456789",
                                                "password": "Keke#Lagos2026"})
    h = auth(r.json()["token"])
    blocked = client.post("/api/rentals", headers=h, json={"vehicle_id": "EC-004", "mode": "half_day"})
    assert blocked.status_code == 403 and "licence" in blocked.json()["detail"]
    assert submit_licence(client, h, kind="learner").status_code == 422
    assert submit_licence(client, h, expires="2020-01-01").status_code == 422
    assert client.get("/api/me/licence", headers=h).json()["self_drive"]["ok"] is False
    with_driver = client.post("/api/rentals", headers=h, json={"vehicle_id": "EC-004", "mode": "half_day", "with_driver": True})
    assert with_driver.status_code == 200
    ok = submit_licence(client, h)
    assert ok.status_code == 200 and ok.json()["self_drive"]["ok"] is True and ok.json()["licence"]["number"] == "LAG12345AA01"


def test_admin_reviews_licences_and_customer_is_told(client, admin):
    from tests.conftest import submit_licence
    r = client.post("/api/auth/register", json={"name": "Tolu Bello", "email": "tolu@test.ng", "phone": "08031112222",
                                                "password": "Tolu#Lagos2026"})
    h = auth(r.json()["token"])
    submit_licence(client, h, number="ABC12345XY99")
    queue = client.get("/api/admin/licences", headers=admin).json()
    lic = next(l for l in queue if l["email"] == "tolu@test.ng")
    assert lic["status"] == "submitted" and lic["has_image"]
    img = client.get(f"/api/admin/licences/{lic['id']}/image", headers=admin)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/admin/licences/{lic['id']}/image", headers=h).status_code == 403
    assert client.post(f"/api/admin/licences/{lic['id']}", headers=admin, json={"status": "rejected"}).status_code == 422
    client.post(f"/api/admin/licences/{lic['id']}", headers=admin, json={"status": "rejected", "note": "Photo is blurred."})
    me = client.get("/api/me/licence", headers=h).json()
    assert me["self_drive"]["ok"] is False and "blurred" in me["self_drive"]["reason"]
    notes = client.get("/api/me/notifications", headers=h).json()
    assert notes["unread"] == 1 and "wasn't accepted" in notes["items"][0]["title"]
    client.post("/api/me/notifications/read", headers=h, json={})
    assert client.get("/api/me/notifications", headers=h).json()["unread"] == 0


def test_speeding_strikes_warn_then_charge(client, customer):
    rental = book(client, customer, vehicle_id="EX-002", mode="half_day")
    code = rental["code"]
    def ping(speed, place="Third Mainland Bridge"):
        r = client.post(f"/api/tracking/{code}/ping", headers=customer, json={"location": place, "lat": 6.5, "lng": 3.4, "speed_kmh": speed})
        assert r.status_code == 200, r.text
    # one long stretch over the limit counts once
    for s in (120, 125, 118):
        ping(s)
    assert client.get(f"/api/rentals/{code}", headers=customer).json()["speeding_events"] == 1
    for _ in range(4):          # four more separate incidents: total 5
        ping(60, "Lekki"); ping(130)
    trip = client.get(f"/api/rentals/{code}", headers=customer).json()
    assert trip["speeding_events"] == 5
    titles = [n["title"] for n in client.get("/api/me/notifications", headers=customer).json()["items"] if n["kind"] == "speeding"]
    assert any("warning 1 of 3" in t for t in titles) and any("Final" in t for t in titles) and any("charge" in t for t in titles)
    s = client.post(f"/api/rentals/{code}/end", headers=customer).json()["settlement"]
    assert s["speeding_incidents"] == 5 and s["speeding_charge"] == 10_000


def test_profile_and_password(client, customer, admin):
    p = client.get("/api/me", headers=customer).json()
    assert p["user"]["email"] == "nuhu@test.ng" and p["self_drive"]["ok"] and p["stats"]["trips"] >= 1
    upd = client.put("/api/me", headers=customer, json={"name": "Nuhu O. Oyibo", "phone": "08039378598"})
    assert upd.status_code == 200 and upd.json()["name"] == "Nuhu O. Oyibo"
    assert client.post("/api/me/password", headers=customer, json={"current_password": "wrong", "new_password": "Another#2026"}).status_code == 403
    assert client.post("/api/me/password", headers=customer, json={"current_password": "Lagos#Drive2026", "new_password": "Another#2026"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "nuhu@test.ng", "password": "Another#2026"}).status_code == 200
    client.post("/api/me/password", headers=customer, json={"current_password": "Another#2026", "new_password": "Lagos#Drive2026"})


def test_admin_can_message_a_driver(client, customer, admin):
    rental = book(client, customer, vehicle_id="EC-009", mode="half_day")
    r = client.post(f"/api/admin/rentals/{rental['code']}/warn", headers=admin, json={})
    assert r.status_code == 200
    items = client.get("/api/me/notifications", headers=customer).json()["items"]
    assert items[0]["kind"] == "staff" and items[0]["rental"] == rental["code"]
    client.post(f"/api/rentals/{rental['code']}/end", headers=customer)


def test_demo_simulator_sends_at_most_five_speeding_notices(client, admin):
    """The GPS simulator stops notifying a customer after 5 speeding notices; admin warnings still get through."""
    from conftest import auth, submit_licence
    from app.database import SessionLocal
    from app.models import Rental
    from app.services import DEMO_AUTO_SPEEDING_NOTICES, record_tracking
    r = client.post("/api/auth/register", json={"name": "Demo Speedster", "email": "speedy@test.ng",
                                                "phone": "08011112222", "password": "Lagos#Speed2026"})
    headers = auth(r.json()["token"])
    assert submit_licence(client, headers).status_code == 200
    code = book(client, headers, vehicle_id="EC-004", mode="half_day")["code"]
    with SessionLocal() as db:
        rental = db.query(Rental).filter_by(code=code).one()
        for _ in range(9):          # nine separate simulated incidents
            record_tracking(db, rental, "Lekki", 6.45, 3.47, 60, simulated=True)
            record_tracking(db, rental, "Lekki", 6.45, 3.47, 130, simulated=True)
        db.commit()
    speeding = [n for n in client.get("/api/me/notifications", headers=headers).json()["items"] if n["kind"] == "speeding"]
    assert len(speeding) == DEMO_AUTO_SPEEDING_NOTICES == 5
    assert client.post(f"/api/admin/rentals/{code}/warn", headers=admin, json={}).status_code == 200
    items = client.get("/api/me/notifications", headers=headers).json()["items"]
    assert items[0]["kind"] == "staff"
    client.post(f"/api/rentals/{code}/end", headers=headers)
