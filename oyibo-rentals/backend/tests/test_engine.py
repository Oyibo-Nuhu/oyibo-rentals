"""The rules carried over from the original OOP project, plus the new ones."""
from datetime import datetime

import pytest

from app import engine as eng

MONDAY_NOON = datetime(2026, 10, 26, 12, 0)   # off-peak
MONDAY_RUSH = datetime(2026, 10, 26, 8, 0)    # weekday morning rush


def car(rate=45_000):
    return eng.build_vehicle("economy", "C1", "Toyota", "Corolla", 2022, rate)


def test_polymorphic_daily_cost_and_encapsulated_rate():
    assert car().calculate_rental_cost(3) == 135_000
    assert not hasattr(car(), "daily_rate")          # rate is private, read through the getter
    assert car().get_daily_rate() == 45_000


@pytest.mark.parametrize("days,pct", [(1, 0), (7, 0.05), (14, 0.10), (30, 0.15)])
def test_multi_day_discounts(days, pct):
    assert eng.multi_day_discount(45_000 * days, days) == pytest.approx(45_000 * days * pct)


def test_cannot_rent_twice_or_return_twice():
    v = car()
    v.rent_vehicle()
    with pytest.raises(ValueError):
        v.rent_vehicle()
    v.return_vehicle()
    with pytest.raises(ValueError):
        v.return_vehicle()


def test_invalid_rental_period_rejected():
    with pytest.raises(ValueError):
        eng.quote_rental(car(), "full_day", MONDAY_NOON, days=0)


def test_tracking_rejects_empty_location_and_flags_speed():
    with pytest.raises(ValueError):
        eng.validate_tracking_update(car(), "   ", 60)
    reading = eng.validate_tracking_update(car(), "Third Mainland Bridge", 120)
    assert reading["over_speed_limit"] is True
    assert eng.validate_tracking_update(car(), "Lekki", 99)["over_speed_limit"] is False


def test_route_trip_lekki_to_surulere_is_timed_and_cheaper_than_go_anywhere():
    route = eng.quote_rental(car(), "route", MONDAY_NOON, pickup="lekki-phase-1", dropoff="surulere")
    half = eng.quote_rental(car(), "half_day", MONDAY_NOON)
    assert route.unit_label == "hours" and route.units >= 1
    assert route.subtotal < half.subtotal


def test_rush_hour_costs_more():
    calm = eng.quote_rental(car(), "route", MONDAY_NOON, pickup="lekki-phase-1", dropoff="surulere")
    rush = eng.quote_rental(car(), "route", MONDAY_RUSH, pickup="lekki-phase-1", dropoff="surulere")
    assert rush.subtotal > calm.subtotal


def test_cross_country_costs_more_than_full_day():
    full = eng.quote_rental(car(), "full_day", MONDAY_NOON, days=2)
    cross = eng.quote_rental(car(), "cross_country", MONDAY_NOON, days=2, destination="ibadan")
    assert cross.subtotal > full.subtotal


def test_keke_cannot_go_cross_country_but_can_do_routes():
    keke = eng.build_vehicle("tricycle", "TK", "Bajaj", "RE", 2023)
    assert isinstance(keke, eng.Motorcycle) and keke.vehicle_type() == "Keke (Tricycle)"
    eng.quote_rental(keke, "route", MONDAY_NOON, pickup="yaba", dropoff="surulere")
    with pytest.raises(ValueError, match="cross country"):
        eng.quote_rental(keke, "cross_country", MONDAY_NOON, days=2, destination="ibadan")


def test_luxury_needs_standard_insurance():
    lux = eng.build_vehicle("luxury", "LX", "Rolls-Royce", "Cullinan", 2024)
    with pytest.raises(ValueError):
        eng.quote_rental(lux, "full_day", MONDAY_NOON, days=1, insurance_plan="basic")


def test_premium_insurance_has_no_excess():
    payout = eng.calculate_claim_payout("premium", 400_000)
    assert payout["customer_pays"] == 0


def test_speeding_charge_starts_after_three_incidents():
    assert [eng.speeding_charge(n) for n in (0, 3, 4, 6)] == [0, 0, 5_000, 15_000]
    s = eng.calculate_settlement(car(), eng.quote_rental(car(), "half_day", MONDAY_NOON).as_dict(),
                                 MONDAY_NOON, MONDAY_NOON, 0, speeding_incidents=5)
    assert s["speeding_charge"] == 10_000 and s["extras_with_vat"] == 10_000


def test_learner_permits_and_expired_licences_are_refused():
    from datetime import date
    today = date(2026, 10, 28)
    with pytest.raises(ValueError, match="Learner"):
        eng.validate_driver_licence("learner", "LAG12345AA01", date(2030, 1, 1), today)
    with pytest.raises(ValueError, match="expired"):
        eng.validate_driver_licence("full", "LAG12345AA01", date(2026, 10, 1), today)
    with pytest.raises(ValueError, match="licence number"):
        eng.validate_driver_licence("full", "12", date(2030, 1, 1), today)
    assert eng.validate_driver_licence("full", "lag-12345 aa01", date(2030, 1, 1), today) == "LAG12345AA01"
