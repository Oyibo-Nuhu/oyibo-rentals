"""Admin data science — grown from rental_dashboard.py.

The data contract, cleaning rules and core charts come from the original
Streamlit dashboard (standardize_rental_data, build_monthly_summary, the KPI
definitions and the by-type / status / distance-duration views). They now run
on live database records and feed the web admin dashboard as JSON.

Added: demand heatmap, rental-mode mix, weekly demand forecast with a
backtest, driver risk scores, customer segments (k-means on recency,
frequency and spend), damage-claim loss ratios and fleet utilization.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.orm import Session

from .engine import SPEED_LIMIT_KMH as SPEED_LIMIT
from .engine import TIER_CLASSES, TIER_ORDER
from .locations import LAGOS_ZONES
from .models import DamageClaim, Rental, Vehicle, lagos_now

CURRENCY = "₦"
ACTIVE_STATUSES = {"currently rented", "rented", "active", "in progress"}
REQUIRED_COLUMNS = {"rental_date", "vehicle_type", "rental_days", "final_cost"}
OPTIONAL_DEFAULTS = {
    "rental_id": None,
    "vehicle_id": "Not provided",
    "mileage_km": 0.0,
    "speeding_events": 0,
    "status": "Returned",
}
COLUMN_ALIASES = {
    "rentalid": "rental_id", "rental_id": "rental_id", "vehicleid": "vehicle_id", "vehicle_id": "vehicle_id",
    "date": "rental_date", "rentaldate": "rental_date", "rental_date": "rental_date",
    "type": "vehicle_type", "vehicletype": "vehicle_type", "vehicle_type": "vehicle_type",
    "days": "rental_days", "duration": "rental_days", "rentaldays": "rental_days", "rental_days": "rental_days",
    "cost": "final_cost", "amount": "final_cost", "totalcost": "final_cost", "finalcost": "final_cost",
    "final_cost": "final_cost", "mileage": "mileage_km", "mileagekm": "mileage_km", "mileage_km": "mileage_km",
    "speedingevents": "speeding_events", "speeding_events": "speeding_events",
    "rentalstatus": "status", "rental_status": "status", "status": "status",
}
STATUS_LABELS = {"active": "Currently Rented", "completed": "Returned", "reserved": "Reserved",
                 "cancelled": "Cancelled", "pending_payment": "Awaiting Payment"}
MODE_LABELS = {"route": "Route (A→B)", "half_day": "Half day", "full_day": "Full day", "cross_country": "Cross country"}


# ---------------------------------------------------------------------------
# From the original dashboard
# ---------------------------------------------------------------------------

def standardize_rental_data(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize common CSV headers and validate rental dashboard fields."""
    cleaned = data.copy()
    cleaned.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in cleaned.columns]
    cleaned = cleaned.rename(columns={c: COLUMN_ALIASES.get(c.replace("_", ""), COLUMN_ALIASES.get(c, c))
                                      for c in cleaned.columns})

    if cleaned.columns.duplicated().any():
        duplicates = cleaned.columns[cleaned.columns.duplicated()].unique().tolist()
        raise ValueError(f"CSV has duplicate columns after normalization: {', '.join(duplicates)}.")
    missing = REQUIRED_COLUMNS - set(cleaned.columns)
    if missing:
        raise ValueError("CSV is missing required columns: " + ", ".join(sorted(missing))
                         + ". Required fields are rental_date, vehicle_type, rental_days, and final_cost.")
    if cleaned.empty:
        raise ValueError("The rental CSV must contain at least one data row.")

    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in cleaned.columns:
            cleaned[column] = default
    if cleaned["rental_id"].isna().any():
        cleaned["rental_id"] = cleaned["rental_id"].fillna(
            pd.Series([f"RENTAL-{i + 1:04d}" for i in range(len(cleaned))], index=cleaned.index))

    cleaned["rental_date"] = pd.to_datetime(cleaned["rental_date"], errors="coerce")
    invalid_dates = cleaned["rental_date"].isna()
    if invalid_dates.any():
        raise ValueError(f"{int(invalid_dates.sum())} rental date value(s) are blank or invalid.")

    cleaned["vehicle_type"] = cleaned["vehicle_type"].astype("string").str.strip()
    if cleaned["vehicle_type"].isna().any() or cleaned["vehicle_type"].eq("").any():
        raise ValueError("Vehicle type cannot be blank.")

    for column in ["rental_days", "final_cost", "mileage_km", "speeding_events"]:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
        if cleaned[column].isna().any():
            raise ValueError(f"{column} must contain valid numeric values.")
        if cleaned[column].isin([float("inf"), float("-inf")]).any():
            raise ValueError(f"{column} must contain finite numeric values.")

    if (cleaned["rental_days"] <= 0).any():
        raise ValueError("Rental days must be greater than zero.")
    if (cleaned[["final_cost", "mileage_km", "speeding_events"]] < 0).any().any():
        raise ValueError("Final cost, mileage, and speeding events cannot be negative.")
    if (cleaned["speeding_events"] % 1 != 0).any():
        raise ValueError("Speeding events must be whole numbers.")

    cleaned["status"] = cleaned["status"].fillna("Returned").astype("string").str.strip()
    cleaned.loc[cleaned["status"].eq(""), "status"] = "Returned"
    cleaned["status"] = cleaned["status"].str.title()
    cleaned["vehicle_id"] = cleaned["vehicle_id"].fillna("Not provided").astype("string")
    return cleaned


def build_monthly_summary(data: pd.DataFrame) -> pd.DataFrame:
    monthly = data.assign(month=data["rental_date"].dt.to_period("M").astype(str))
    return (monthly.groupby("month", as_index=False)
            .agg(revenue=("final_cost", "sum"), rentals=("rental_id", "nunique"))
            .sort_values("month"))


def core_report(df: pd.DataFrame) -> dict:
    """The original dashboard's KPIs and four charts, as JSON."""
    if df.empty:
        return {"empty": True}
    kpis = {
        "total_revenue": float(df["final_cost"].sum()),
        "rental_count": int(df["rental_id"].nunique()),
        "average_days": float(df["rental_days"].mean()),
        "active_count": int(df["status"].str.casefold().isin(ACTIVE_STATUSES).sum()),
        "speeding_events": int(df["speeding_events"].sum()),
    }
    monthly = build_monthly_summary(df)
    by_type = (df.groupby("vehicle_type", as_index=False)
               .agg(revenue=("final_cost", "sum"), rentals=("rental_id", "nunique"),
                    average_charge=("final_cost", "mean")).sort_values("revenue"))
    by_status = (df.groupby("status", as_index=False).agg(rentals=("rental_id", "nunique"))
                 .sort_values("rentals", ascending=False))
    sample = df.sample(min(len(df), 600), random_state=7) if len(df) > 600 else df
    return {
        "empty": False,
        "kpis": kpis,
        "monthly": records(monthly),
        "by_type": records(by_type),
        "by_status": records(by_status),
        "scatter": records(sample[["rental_id", "vehicle_type", "rental_days", "mileage_km",
                                   "final_cost", "speeding_events", "status"]]),
    }


# ---------------------------------------------------------------------------
# Live data
# ---------------------------------------------------------------------------

def records(frame: pd.DataFrame) -> list[dict]:
    out = frame.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    out = out.replace({np.nan: None})
    return [{k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()} for row in out.to_dict("records")]


def rentals_frame(db: Session) -> pd.DataFrame:
    rows = db.scalars(select(Rental).where(Rental.status.in_(("active", "completed", "reserved")))).all()
    data = []
    for r in rows:
        hours = (r.end_at - r.start_at).total_seconds() / 3600
        if r.actual_end_at:
            hours = max(hours, (r.actual_end_at - r.start_at).total_seconds() / 3600)
        data.append({
            "rental_id": r.code,
            "pickup_key": r.pickup_key,
            "vehicle_id": r.vehicle_id,
            "rental_date": r.start_at,
            "vehicle_type": TIER_CLASSES[r.vehicle.tier].TIER_LABEL,
            "tier": r.vehicle.tier,
            "rental_days": round(max(hours / 24, 1 / 24), 3),
            "hours": hours,
            "final_cost": float(r.final_cost if r.final_cost is not None else r.total_due),
            "mileage_km": round(r.distance_km, 1),
            "speeding_events": r.speeding_events,
            "status": STATUS_LABELS.get(r.status, r.status.title()),
            "mode": r.mode,
            "zone": LAGOS_ZONES[r.pickup_key].name if r.pickup_key else None,
            "customer_id": r.user_id,
            "customer": r.user.name,
            "insurance_plan": r.insurance_plan,
            "insurance_fee": float(r.quote.get("insurance_fee", 0)),
            "late": bool(r.settlement and r.settlement.get("late_units", 0) > 0),
            "max_speed": r.max_speed,
            "rating": r.rating,
            "with_driver": r.with_driver,
            "is_electric": r.vehicle.is_electric,
        })
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df["rental_date"] = pd.to_datetime(df["rental_date"])
    return df


def export_csv(db: Session) -> str:
    df = rentals_frame(db)
    cols = ["rental_id", "vehicle_id", "rental_date", "vehicle_type", "rental_days", "mileage_km",
            "final_cost", "speeding_events", "status", "mode", "insurance_plan"]
    return "" if df.empty else df[cols].to_csv(index=False)


def weekly_forecast(df: pd.DataFrame, horizon: int = 8) -> dict:
    """Ridge regression on trend + yearly seasonality + December effect.

    Reports a backtest on the most recent 8 weeks so the forecast's error is visible.
    """
    weekly = df.set_index("rental_date").resample("W-MON")["rental_id"].nunique().rename("rentals")
    weekly = weekly.iloc[:-1] if len(weekly) > 1 else weekly   # drop the incomplete current week
    if len(weekly) < 16:
        return {"available": False, "reason": "Needs at least 16 weeks of history."}

    def features(index: pd.DatetimeIndex, t0: pd.Timestamp) -> np.ndarray:
        t = ((index - t0).days / 7).to_numpy(dtype=float)
        doy = index.dayofyear.to_numpy(dtype=float)
        return np.column_stack([t, np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25),
                                (index.month == 12).astype(float)])

    t0 = weekly.index[0]
    X, y = features(weekly.index, t0), weekly.to_numpy(dtype=float)
    hold = 8
    back = Ridge(alpha=1.0).fit(X[:-hold], y[:-hold])
    back_pred = back.predict(X[-hold:])
    mae = float(np.mean(np.abs(back_pred - y[-hold:])))

    model = Ridge(alpha=1.0).fit(X, y)
    resid_sd = float(np.std(y - model.predict(X), ddof=1))
    future = pd.date_range(weekly.index[-1] + timedelta(weeks=1), periods=horizon, freq="W-MON")
    pred = np.clip(model.predict(features(future, t0)), 0, None)
    return {
        "available": True,
        "history": [{"week": d.strftime("%Y-%m-%d"), "rentals": int(v)} for d, v in weekly.items()],
        "forecast": [{"week": d.strftime("%Y-%m-%d"), "rentals": round(float(p), 1),
                      "low": round(max(0.0, p - 1.96 * resid_sd), 1), "high": round(float(p + 1.96 * resid_sd), 1)}
                     for d, p in zip(future, pred)],
        "backtest_mae": round(mae, 1),
        "method": "Ridge regression on weekly rentals with trend, yearly seasonality and a December effect.",
    }


def driver_risk(df: pd.DataFrame, claims: pd.DataFrame) -> list[dict]:
    """Transparent 0–100 risk score from speeding rate, top speed, late returns and claims."""
    g = df.groupby(["customer_id", "customer"]).agg(
        trips=("rental_id", "nunique"), km=("mileage_km", "sum"), speeding=("speeding_events", "sum"),
        max_speed=("max_speed", "max"), late_rate=("late", "mean")).reset_index()
    g = g[g["trips"] >= 2]
    if g.empty:
        return []
    claim_counts = claims.groupby("customer_id").size() if not claims.empty else pd.Series(dtype=float)
    g["claims"] = g["customer_id"].map(claim_counts).fillna(0)
    g["speeding_per_100km"] = g["speeding"] / g["km"].clip(lower=1) * 100
    parts = {"speeding_per_100km": 0.4, "max_speed": 0.25, "late_rate": 0.15, "claims": 0.2}
    g["risk_score"] = sum(g[c].rank(pct=True) * w for c, w in parts.items()) * 100
    g["band"] = pd.cut(g["risk_score"], [-1, 40, 70, 101], labels=["Low", "Medium", "High"]).astype(str)
    top = g.sort_values("risk_score", ascending=False).head(15)
    return records(top[["customer", "trips", "km", "speeding", "speeding_per_100km", "max_speed",
                        "late_rate", "claims", "risk_score", "band"]].round(2))


def customer_segments(df: pd.DataFrame) -> dict:
    """K-means on recency, frequency and spend (log-scaled, standardized)."""
    now = df["rental_date"].max()
    rfm = df.groupby(["customer_id", "customer"]).agg(
        recency_days=("rental_date", lambda s: (now - s.max()).days),
        frequency=("rental_id", "nunique"), spend=("final_cost", "sum")).reset_index()
    if len(rfm) < 8:
        return {"available": False}
    X = StandardScaler().fit_transform(np.log1p(rfm[["recency_days", "frequency", "spend"]]))
    k = 4
    rfm["cluster"] = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(X)
    prof = rfm.groupby("cluster").agg(customers=("customer_id", "count"), recency_days=("recency_days", "mean"),
                                      frequency=("frequency", "mean"), spend=("spend", "mean"))
    z = (prof - prof.mean()) / prof.std(ddof=0).replace(0, 1)
    score = z["frequency"] + z["spend"] - z["recency_days"]
    names = ["VIP regulars", "Loyal riders", "Occasional riders", "At risk of churning"]
    ranking = {c: names[i] for i, c in enumerate(score.sort_values(ascending=False).index)}
    # a cluster that is clearly stale is "at risk" whatever its spend
    stale = prof["recency_days"].idxmax()
    if ranking[stale] != "At risk of churning":
        other = next(c for c, n in ranking.items() if n == "At risk of churning")
        ranking[other], ranking[stale] = ranking[stale], "At risk of churning"
    rfm["segment"] = rfm["cluster"].map(ranking)
    prof["segment"] = prof.index.map(ranking)
    return {
        "available": True,
        "profiles": records(prof.reset_index(drop=True).round(1)),
        "points": records(rfm[["customer", "recency_days", "frequency", "spend", "segment"]].round(0)),
    }


def apply_filters(df: pd.DataFrame, start=None, end=None, tiers=None, modes=None, zone=None) -> pd.DataFrame:
    out = df
    if start is not None:
        out = out[out["rental_date"] >= pd.Timestamp(start)]
    if end is not None:
        out = out[out["rental_date"] < pd.Timestamp(end) + pd.Timedelta(days=1)]
    if tiers:
        out = out[out["tier"].isin(tiers)]
    if modes:
        out = out[out["mode"].isin(modes)]
    if zone:
        out = out[out["pickup_key"] == zone]
    return out


def insights(df: pd.DataFrame, report: dict) -> list[dict]:
    """Plain-language findings computed from the filtered data. Each one names the number behind it."""
    out = []
    tmp = df.assign(dow=df["rental_date"].dt.day_name(), hour=df["rental_date"].dt.hour)
    busiest = tmp.groupby(["dow", "hour"]).size()
    if not busiest.empty:
        (d, h), n = busiest.idxmax(), int(busiest.max())
        out.append({"icon": "clock", "title": f"{d}s around {h % 12 or 12}{'am' if h < 12 else 'pm'} are your busiest",
                    "detail": f"{n} bookings started in that hour slot. Have cars ready nearby."})
    by_tier = df.groupby("vehicle_type").agg(rev=("final_cost", "sum"), n=("rental_id", "nunique"))
    if len(by_tier) > 1:
        top = by_tier["rev"].idxmax()
        rev_share, trip_share = by_tier.loc[top, "rev"] / by_tier["rev"].sum(), by_tier.loc[top, "n"] / by_tier["n"].sum()
        out.append({"icon": "crown", "title": f"{top} earns {rev_share:.0%} of revenue",
                    "detail": f"…from only {trip_share:.0%} of trips."})
    sp = tmp.groupby("hour")["speeding_events"].sum()
    if sp.sum() > 0:
        h = int(sp.idxmax())
        out.append({"icon": "gauge", "title": f"Speeding peaks for trips starting at {h % 12 or 12}{'am' if h < 12 else 'pm'}",
                    "detail": f"{int(sp.max())} alerts over {SPEED_LIMIT} km/h. Consider a reminder push before those trips."})
    f = report.get("forecast") or {}
    if f.get("available") and f["forecast"]:
        nxt = f["forecast"][0]
        out.append({"icon": "trend", "title": f"About {round(nxt['rentals'])} rentals expected next week",
                    "detail": f"95% range {round(nxt['low'])}–{round(nxt['high'])}. Backtest error ±{f['backtest_mae']} a week."})
    idle = [u for u in report.get("utilization", []) if u["utilization"] == 0]
    if idle:
        out.append({"icon": "parking", "title": f"{len(idle)} vehicle{'s' if len(idle) != 1 else ''} had no bookings in 30 days",
                    "detail": ", ".join(u["vehicle"] for u in idle[:3]) + ("…" if len(idle) > 3 else "") + ". Reprice, promote or relocate."})
    ev = df[df["is_electric"]]
    if len(ev):
        out.append({"icon": "leaf", "title": f"Electric rides are {len(ev) / len(df):.0%} of trips",
                    "detail": f"{naira_text(ev['final_cost'].sum())} earned from EVs and Spiro bikes."})
    return out


def naira_text(v: float) -> str:
    return f"{CURRENCY}{v / 1e6:,.1f}M" if v >= 1e6 else f"{CURRENCY}{v:,.0f}"


def full_report(db: Session, start=None, end=None, tiers=None, modes=None, zone=None) -> dict:
    from .services import fleet_photos  # local import: services imports models too

    everything = rentals_frame(db)
    if everything.empty:
        return {"empty": True}
    options = {
        "min_date": everything["rental_date"].min().strftime("%Y-%m-%d"),
        "max_date": everything["rental_date"].max().strftime("%Y-%m-%d"),
        "tiers": [{"key": t, "label": TIER_CLASSES[t].TIER_LABEL} for t in TIER_ORDER if t in set(everything["tier"])],
        "modes": [{"key": k, "label": v} for k, v in MODE_LABELS.items()],
        "zones": [{"key": k, "name": z.name} for k, z in LAGOS_ZONES.items() if k in set(everything["pickup_key"].dropna())],
    }
    df = apply_filters(everything, start, end, tiers, modes, zone)
    filters = {"start": start, "end": end, "tiers": tiers or [], "modes": modes or [], "zone": zone}
    if df.empty:
        return {"empty": False, "no_match": True, "options": options, "filters": filters}
    report = core_report(df)
    report["options"], report["filters"] = options, filters

    now = lagos_now() if end is None else min(lagos_now(), pd.Timestamp(end).to_pydatetime() + timedelta(days=1))
    last30 = df[df["rental_date"] >= now - timedelta(days=30)]["final_cost"].sum()
    prev30 = df[(df["rental_date"] < now - timedelta(days=30)) & (df["rental_date"] >= now - timedelta(days=60))]["final_cost"].sum()
    fleet = db.scalars(select(Vehicle)).all()
    report["kpis"].update({
        "revenue_30d": float(last30),
        "revenue_growth": float((last30 - prev30) / prev30) if prev30 else None,
        "fleet_size": len(fleet),
        "fleet_on_road": sum(1 for v in fleet if v.status == "rented"),
        "average_rating": float(df["rating"].dropna().mean()) if df["rating"].notna().any() else None,
        "customers": int(df["customer_id"].nunique()),
    })

    # Rental mode mix
    report["by_mode"] = records(df.groupby("mode").agg(rentals=("rental_id", "nunique"), revenue=("final_cost", "sum"),
                                                       avg_charge=("final_cost", "mean")).reset_index()
                                .assign(mode=lambda d: d["mode"].map(MODE_LABELS)))

    # Demand heatmap: weekday × hour
    tmp = df.assign(dow=df["rental_date"].dt.dayofweek, hour=df["rental_date"].dt.hour)
    grid = tmp.pivot_table(index="dow", columns="hour", values="rental_id", aggfunc="count", fill_value=0)
    grid = grid.reindex(index=range(7), columns=range(24), fill_value=0)
    report["heatmap"] = {"days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "hours": list(range(24)),
                         "values": grid.to_numpy().astype(int).tolist()}

    zones = df.dropna(subset=["zone"]).groupby("zone").agg(rentals=("rental_id", "nunique"),
                                                           revenue=("final_cost", "sum")).reset_index()
    report["top_zones"] = records(zones.sort_values("rentals", ascending=False).head(12))

    # Speeding by hour of day
    report["speeding_by_hour"] = records(tmp.groupby("hour").agg(events=("speeding_events", "sum"),
                                                                 rentals=("rental_id", "nunique")).reset_index())

    # Claims and insurance
    claim_rows = db.scalars(select(DamageClaim)).all()
    claims = pd.DataFrame([{"rental_id": c.rental.code, "customer_id": c.rental.user_id, "tier": c.rental.vehicle.tier,
                            "plan": c.rental.insurance_plan, "damage_cost": c.damage_cost,
                            "insurer_pays": c.insurer_pays, "status": c.status} for c in claim_rows])
    if not claims.empty:
        claims = claims[claims["rental_id"].isin(set(df["rental_id"]))]
    premiums = df.groupby("insurance_plan")["insurance_fee"].sum()
    if not claims.empty:
        by_plan = claims.groupby("plan").agg(claims=("damage_cost", "count"), damage=("damage_cost", "sum"),
                                             paid=("insurer_pays", "sum")).reindex(premiums.index, fill_value=0)
    else:
        by_plan = pd.DataFrame(0, index=premiums.index, columns=["claims", "damage", "paid"])
    by_plan["premiums"] = premiums
    by_plan["loss_ratio"] = by_plan["paid"] / by_plan["premiums"].replace(0, np.nan)
    report["claims"] = {
        "by_plan": records(by_plan.reset_index().rename(columns={"insurance_plan": "plan", "index": "plan"}).round(3)),
        "claim_rate": float(len(claims) / df["rental_id"].nunique()),
        "open": int((claims["status"] == "open").sum()) if not claims.empty else 0,
    }

    # Fleet utilization, last 30 days
    recent = df[df["rental_date"] >= now - timedelta(days=30)]
    util = recent.groupby("vehicle_id")["hours"].sum() / (30 * 24)
    fleet_rows = [{"vehicle_id": v.id, "vehicle": f"{v.brand} {v.model}", "tier": v.tier,
                   "utilization": round(float(min(util.get(v.id, 0.0), 1.0)), 3)}
                  for v in fleet if not tiers or v.tier in tiers]
    report["utilization"] = sorted(fleet_rows, key=lambda r: r["utilization"], reverse=True)

    report["forecast"] = weekly_forecast(df)
    report["driver_risk"] = driver_risk(df, claims)
    report["segments"] = customer_segments(df)
    report["ev_share"] = float(df["is_electric"].mean())

    # Weekly sparklines for the KPI tiles (last 12 full weeks in view)
    wk = df.set_index("rental_date").resample("W-MON").agg({"final_cost": "sum", "rental_id": "nunique", "speeding_events": "sum"})
    wk = wk.tail(12)
    report["spark"] = {"revenue": [round(float(v)) for v in wk["final_cost"]], "rentals": [int(v) for v in wk["rental_id"]],
                       "speeding": [int(v) for v in wk["speeding_events"]]}

    # Bar-chart race: cumulative revenue by class, month by month
    m = df.assign(month=df["rental_date"].dt.to_period("M").astype(str)).pivot_table(
        index="month", columns="tier", values="final_cost", aggfunc="sum", fill_value=0).sort_index().cumsum()
    report["race"] = {"months": list(m.index), "tiers": [{"key": t, "label": TIER_CLASSES[t].TIER_LABEL} for t in TIER_ORDER if t in m.columns],
                      "values": {t: [round(float(v)) for v in m[t]] for t in m.columns}}

    # Daily revenue calendar (last 53 weeks in view)
    day = df.set_index("rental_date").resample("D").agg({"final_cost": "sum", "rental_id": "nunique"}).tail(371)
    report["calendar"] = [{"date": d.strftime("%Y-%m-%d"), "revenue": round(float(r.final_cost)), "rentals": int(r.rental_id)}
                          for d, r in day.iterrows()]

    # Pickup map: bubbles per zone
    zm = df.dropna(subset=["pickup_key"]).groupby("pickup_key").agg(rentals=("rental_id", "nunique"), revenue=("final_cost", "sum"),
                                                                   speeding=("speeding_events", "sum"))
    report["zone_map"] = [{"key": k, "name": LAGOS_ZONES[k].name, "lat": LAGOS_ZONES[k].lat, "lng": LAGOS_ZONES[k].lng,
                           "rentals": int(r.rentals), "revenue": round(float(r.revenue)), "speeding": int(r.speeding)}
                          for k, r in zm.iterrows() if k in LAGOS_ZONES]

    # Fleet podium: top earners with their photos
    photos = fleet_photos()
    names = {v.id: v for v in fleet}
    top = df.groupby("vehicle_id").agg(revenue=("final_cost", "sum"), rentals=("rental_id", "nunique"),
                                       km=("mileage_km", "sum")).sort_values("revenue", ascending=False).head(5)
    report["podium"] = [{"vehicle_id": vid, "vehicle": f"{names[vid].brand} {names[vid].model}" if vid in names else vid,
                         "tier": names[vid].tier if vid in names else "", "revenue": round(float(r.revenue)),
                         "rentals": int(r.rentals), "km": round(float(r.km)),
                         "photo": f"/static/{photos[vid]['file']}" if vid in photos else None}
                        for vid, r in top.iterrows()]

    # Baseline for the pricing simulator: last 30 days in view, per class
    base = df[df["rental_date"] >= now - timedelta(days=30)]
    if base.empty:
        base = df
    report["simulator_base"] = [{"tier": t, "label": TIER_CLASSES[t].TIER_LABEL, "rentals": int(g["rental_id"].nunique()),
                                 "revenue": round(float(g["final_cost"].sum()))} for t, g in base.groupby("tier")]
    report["by_tier_key"] = records(df.groupby(["tier", "vehicle_type"], as_index=False)
                                    .agg(revenue=("final_cost", "sum"), rentals=("rental_id", "nunique"), average_charge=("final_cost", "mean")))
    report["by_mode_key"] = records(df.groupby("mode", as_index=False).agg(rentals=("rental_id", "nunique"), revenue=("final_cost", "sum"),
                                                                           avg_charge=("final_cost", "mean")))
    report["insights"] = insights(df, report)
    report["generated_at"] = lagos_now().isoformat() + "+01:00"
    return report
