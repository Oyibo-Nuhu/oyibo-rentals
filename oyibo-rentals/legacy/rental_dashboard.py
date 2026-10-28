from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st


CURRENCY = "₦"
REQUIRED_COLUMNS = {"rental_date", "vehicle_type", "rental_days", "final_cost"}
OPTIONAL_DEFAULTS = {
    "rental_id": None,
    "vehicle_id": "Not provided",
    "mileage_km": 0.0,
    "speeding_events": 0,
    "status": "Returned",
}
COLUMN_ALIASES = {
    "rentalid": "rental_id",
    "rental_id": "rental_id",
    "vehicleid": "vehicle_id",
    "vehicle_id": "vehicle_id",
    "date": "rental_date",
    "rentaldate": "rental_date",
    "rental_date": "rental_date",
    "type": "vehicle_type",
    "vehicletype": "vehicle_type",
    "vehicle_type": "vehicle_type",
    "days": "rental_days",
    "duration": "rental_days",
    "rentaldays": "rental_days",
    "rental_days": "rental_days",
    "cost": "final_cost",
    "amount": "final_cost",
    "totalcost": "final_cost",
    "finalcost": "final_cost",
    "final_cost": "final_cost",
    "mileage": "mileage_km",
    "mileagekm": "mileage_km",
    "mileage_km": "mileage_km",
    "speedingevents": "speeding_events",
    "speeding_events": "speeding_events",
    "rentalstatus": "status",
    "rental_status": "status",
    "status": "status",
}


def make_demo_data() -> pd.DataFrame:
    """Create reproducible example records; these are not real customer data."""
    today = date.today()
    vehicle_types = [
        ("Car", 10000),
        ("Motorcycle", 5000),
        ("Truck", 20000),
    ]
    rows = []

    for index in range(30):
        vehicle_type, daily_rate = vehicle_types[index % len(vehicle_types)]
        rental_days = 2 + (index * 3 % 12)
        mileage_km = 45 + (index * 37 % 420)
        active = index % 7 == 0
        rental_date = today - timedelta(days=(index * 4) % 120)
        rows.append(
            {
                "rental_id": f"DEMO-{index + 1:03d}",
                "vehicle_id": f"{vehicle_type[:1].upper()}{index % 8 + 1:03d}",
                "rental_date": rental_date,
                "vehicle_type": vehicle_type,
                "rental_days": rental_days,
                "mileage_km": mileage_km,
                "final_cost": daily_rate * rental_days + 50000,
                "speeding_events": (index % 4) if vehicle_type == "Car" else 0,
                "status": "Currently Rented" if active else "Returned",
            }
        )

    return pd.DataFrame(rows)


def standardize_rental_data(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize common CSV headers and validate rental dashboard fields."""
    cleaned = data.copy()
    cleaned.columns = [
        str(column).strip().lower().replace(" ", "_").replace("-", "_")
        for column in cleaned.columns
    ]
    cleaned = cleaned.rename(
        columns={
            column: COLUMN_ALIASES.get(column.replace("_", ""), COLUMN_ALIASES.get(column, column))
            for column in cleaned.columns
        }
    )

    if cleaned.columns.duplicated().any():
        duplicates = cleaned.columns[cleaned.columns.duplicated()].unique().tolist()
        raise ValueError(f"CSV has duplicate columns after normalization: {', '.join(duplicates)}.")

    missing_columns = REQUIRED_COLUMNS - set(cleaned.columns)
    if missing_columns:
        raise ValueError(
            "CSV is missing required columns: "
            + ", ".join(sorted(missing_columns))
            + ". Required fields are rental_date, vehicle_type, rental_days, and final_cost."
        )
    if cleaned.empty:
        raise ValueError("The rental CSV must contain at least one data row.")

    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in cleaned.columns:
            cleaned[column] = default

    if cleaned["rental_id"].isna().any():
        cleaned["rental_id"] = cleaned["rental_id"].fillna(
            pd.Series(
                [f"RENTAL-{index + 1:04d}" for index in range(len(cleaned))],
                index=cleaned.index,
            )
        )

    cleaned["rental_date"] = pd.to_datetime(cleaned["rental_date"], errors="coerce")
    invalid_dates = cleaned["rental_date"].isna()
    if invalid_dates.any():
        raise ValueError(f"{int(invalid_dates.sum())} rental date value(s) are blank or invalid.")

    cleaned["vehicle_type"] = cleaned["vehicle_type"].astype("string").str.strip()
    if cleaned["vehicle_type"].isna().any() or cleaned["vehicle_type"].eq("").any():
        raise ValueError("Vehicle type cannot be blank.")

    numeric_columns = ["rental_days", "final_cost", "mileage_km", "speeding_events"]
    for column in numeric_columns:
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


def money(value: float) -> str:
    return f"{CURRENCY}{value:,.0f}"


def build_monthly_summary(data: pd.DataFrame) -> pd.DataFrame:
    monthly = data.assign(month=data["rental_date"].dt.to_period("M").astype(str))
    return (
        monthly.groupby("month", as_index=False)
        .agg(revenue=("final_cost", "sum"), rentals=("rental_id", "nunique"))
        .sort_values("month")
    )


def main() -> None:
    st.set_page_config(
        page_title="Rental fleet dashboard",
        page_icon=":material/directions_car:",
        layout="wide",
    )
    st.title("Rental fleet dashboard")
    st.caption(
        "Explore rental activity, recorded charges, and fleet trends. "
        "Hover over any KPI label or chart mark for definitions and details."
    )

    with st.sidebar:
        st.header("Data and filters")
        uploaded_file = st.file_uploader(
            "Upload rental data (CSV)",
            type=["csv"],
            help="Required columns: rental_date, vehicle_type, rental_days, final_cost.",
        )
        st.download_button(
            "Download CSV example",
            data=make_demo_data().to_csv(index=False).encode("utf-8"),
            file_name="rental_dashboard_example.csv",
            mime="text/csv",
            help="Download a sample with the columns this dashboard understands.",
        )

    if uploaded_file is None:
        source_data = make_demo_data()
        st.info("Showing synthetic example data. Upload a rental CSV in the sidebar to analyze your records.")
    else:
        try:
            source_data = pd.read_csv(BytesIO(uploaded_file.getvalue()))
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as error:
            st.error(f"Could not read the uploaded CSV: {error}")
            st.stop()

    try:
        rentals = standardize_rental_data(source_data)
    except ValueError as error:
        st.error(str(error))
        st.stop()

    min_date = rentals["rental_date"].min().date()
    max_date = rentals["rental_date"].max().date()

    with st.sidebar:
        selected_dates = st.date_input(
            "Rental date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            help="Filters rentals by their start date.",
        )
        selected_types = st.multiselect(
            "Vehicle types",
            options=sorted(rentals["vehicle_type"].unique().tolist()),
            default=sorted(rentals["vehicle_type"].unique().tolist()),
        )
        selected_statuses = st.multiselect(
            "Rental statuses",
            options=sorted(rentals["status"].unique().tolist()),
            default=sorted(rentals["status"].unique().tolist()),
        )

    if isinstance(selected_dates, (tuple, list)):
        if len(selected_dates) == 2:
            start_date, end_date = selected_dates
        elif len(selected_dates) == 1:
            start_date = end_date = selected_dates[0]
        else:
            start_date, end_date = min_date, max_date
    else:
        start_date = end_date = selected_dates

    filtered = rentals.loc[
        rentals["rental_date"].dt.date.between(start_date, end_date)
        & rentals["vehicle_type"].isin(selected_types)
        & rentals["status"].isin(selected_statuses)
    ].copy()

    with st.expander("How to interpret this dashboard", icon=":material/info:"):
        st.markdown(
            "- **Total rental charges** sums the uploaded `final_cost` values; it is not profit.\n"
            "- **Average rental days** is the mean of the recorded `rental_days` field.\n"
            "- **Speeding events** uses the uploaded `speeding_events` field. Missing values default to zero, "
            "so treat this as unavailable rather than proof of no speeding when your source has no tracking data.\n"
            "- Charts describe only the filtered records. Demo data is synthetic."
        )

    if filtered.empty:
        st.warning("No rentals match the selected filters. Change the date, vehicle type, or status filters.")
        return

    total_revenue = float(filtered["final_cost"].sum())
    rental_count = int(filtered["rental_id"].nunique())
    average_days = float(filtered["rental_days"].mean())
    speeding_events = float(filtered["speeding_events"].sum())
    active_count = int(filtered["status"].str.casefold().isin(
        {"currently rented", "rented", "active", "in progress"}
    ).sum())

    with st.container(horizontal=True):
        st.metric(
            "Total rental charges",
            money(total_revenue),
            help="Sum of final_cost across filtered rental records. This is recorded charge value, not net profit.",
            border=True,
        )
        st.metric(
            "Rental records",
            f"{rental_count:,}",
            help="Number of unique rental IDs in the filtered records.",
            border=True,
        )
        st.metric(
            "Average rental days",
            f"{average_days:.1f} days",
            help="Arithmetic mean of rental_days across the filtered records.",
            border=True,
        )
        st.metric(
            "Currently rented",
            f"{active_count:,}",
            help="Filtered records whose status is Currently Rented, Rented, Active, or In Progress.",
            border=True,
        )
        st.metric(
            "Speeding events",
            f"{speeding_events:,.0f}",
            help="Sum of recorded speeding_events. This depends on tracking data being present in the source.",
            border=True,
        )

    revenue_column, type_column = st.columns(2)
    with revenue_column:
        with st.container(border=True):
            st.subheader("Monthly rental charges")
            st.caption("How the chart is calculated: sum final_cost by rental start month.")
            monthly = build_monthly_summary(filtered)
            revenue_chart = px.line(
                monthly,
                x="month",
                y="revenue",
                markers=True,
                custom_data=["rentals"],
                labels={"month": "Rental month", "revenue": "Rental charges (₦)"},
            )
            revenue_chart.update_traces(
                hovertemplate=(
                    "<b>%{x}</b><br>Rental charges: ₦%{y:,.0f}"
                    "<br>Rental records: %{customdata[0]}<extra></extra>"
                )
            )
            revenue_chart.update_layout(
                hovermode="x unified",
                margin={"t": 15, "b": 10, "l": 10, "r": 10},
            )
            st.plotly_chart(revenue_chart, width="stretch")
            st.caption(
                f"Interpretation: charges total {money(total_revenue)} over "
                f"{len(monthly)} month(s) in this filtered view."
            )

    with type_column:
        with st.container(border=True):
            st.subheader("Charges by vehicle type")
            st.caption("Bar length is total charges; hover to compare rental count and average charge.")
            by_type = (
                filtered.groupby("vehicle_type", as_index=False)
                .agg(
                    revenue=("final_cost", "sum"),
                    rentals=("rental_id", "nunique"),
                    average_charge=("final_cost", "mean"),
                )
                .sort_values("revenue")
            )
            type_chart = px.bar(
                by_type,
                x="revenue",
                y="vehicle_type",
                orientation="h",
                custom_data=["rentals", "average_charge"],
                labels={"revenue": "Rental charges (₦)", "vehicle_type": "Vehicle type"},
            )
            type_chart.update_traces(
                hovertemplate=(
                    "<b>%{y}</b><br>Total charges: ₦%{x:,.0f}"
                    "<br>Rental records: %{customdata[0]}"
                    "<br>Average charge: ₦%{customdata[1]:,.0f}<extra></extra>"
                )
            )
            type_chart.update_layout(margin={"t": 15, "b": 10, "l": 10, "r": 10})
            st.plotly_chart(type_chart, width="stretch")
            top_type = by_type.sort_values("revenue", ascending=False).iloc[0]
            st.caption(
                f"Interpretation: {top_type['vehicle_type']} has the highest charges "
                f"({money(float(top_type['revenue']))}) in the selected records."
            )

    status_column, profile_column = st.columns(2)
    with status_column:
        with st.container(border=True):
            st.subheader("Rental status mix")
            st.caption("Each segment represents the share of filtered rental records in a status.")
            by_status = (
                filtered.groupby("status", as_index=False)
                .agg(rentals=("rental_id", "nunique"))
                .sort_values("rentals", ascending=False)
            )
            status_chart = px.pie(
                by_status,
                names="status",
                values="rentals",
                hole=0.55,
                custom_data=["rentals"],
                labels={"status": "Rental status", "rentals": "Rental records"},
            )
            status_chart.update_traces(
                hovertemplate=(
                    "<b>%{label}</b><br>Rental records: %{value}"
                    "<br>Share: %{percent}<extra></extra>"
                )
            )
            status_chart.update_layout(margin={"t": 15, "b": 10, "l": 10, "r": 10})
            st.plotly_chart(status_chart, width="stretch")
            st.caption("Interpretation: status shares use unique rental IDs as the denominator.")

    with profile_column:
        with st.container(border=True):
            st.subheader("Rental distance and duration")
            st.caption("Each point is a rental. Hover to inspect its ID, days, mileage, charge, and speed events.")
            profile_chart = px.scatter(
                filtered,
                x="rental_days",
                y="mileage_km",
                color="vehicle_type",
                custom_data=["rental_id", "final_cost", "speeding_events", "status"],
                labels={
                    "rental_days": "Rental days",
                    "mileage_km": "Mileage (km)",
                    "vehicle_type": "Vehicle type",
                },
            )
            profile_chart.update_traces(
                hovertemplate=(
                    "<b>Rental %{customdata[0]}</b><br>Vehicle type: %{fullData.name}"
                    "<br>Duration: %{x:.1f} days<br>Mileage: %{y:,.1f} km"
                    "<br>Recorded charge: ₦%{customdata[1]:,.0f}"
                    "<br>Speeding events: %{customdata[2]}"
                    "<br>Status: %{customdata[3]}<extra></extra>"
                )
            )
            profile_chart.update_layout(margin={"t": 15, "b": 10, "l": 10, "r": 10})
            st.plotly_chart(profile_chart, width="stretch")
            st.caption(
                "Interpretation: points farther right are longer rentals; points higher up have more mileage. "
                "This view can help identify unusual combinations for follow-up."
            )

    with st.container(border=True):
        st.subheader("Filtered rental records")
        st.caption(
            f"Showing {len(filtered):,} row(s) from {start_date:%Y-%m-%d} "
            f"to {end_date:%Y-%m-%d}. Hover the column names for field definitions."
        )
        display_data = filtered.sort_values("rental_date", ascending=False).rename(
            columns={
                "rental_id": "Rental ID",
                "vehicle_id": "Vehicle ID",
                "rental_date": "Rental date",
                "vehicle_type": "Vehicle type",
                "rental_days": "Rental days",
                "mileage_km": "Mileage (km)",
                "final_cost": "Final cost (₦)",
                "speeding_events": "Speeding events",
                "status": "Status",
            }
        )
        st.dataframe(
            display_data,
            hide_index=True,
            column_config={
                "Rental ID": st.column_config.TextColumn(
                    "Rental ID", help="Unique identifier for this rental."
                ),
                "Vehicle ID": st.column_config.TextColumn(
                    "Vehicle ID", help="Vehicle identifier, if included in the source data."
                ),
                "Vehicle type": st.column_config.TextColumn(
                    "Vehicle type", help="Category of vehicle rented."
                ),
                "Rental date": st.column_config.DatetimeColumn(
                    "Rental date", format="YYYY-MM-DD", help="Date the rental began."
                ),
                "Rental days": st.column_config.NumberColumn(
                    "Rental days", help="Recorded length of the rental in days."
                ),
                "Mileage (km)": st.column_config.NumberColumn(
                    "Mileage (km)", format="%.1f", help="Recorded distance driven in kilometers."
                ),
                "Final cost (₦)": st.column_config.NumberColumn(
                    "Final cost (₦)", format="₦%.2f", help="Recorded total charge for this rental."
                ),
                "Speeding events": st.column_config.NumberColumn(
                    "Speeding events",
                    help="Count of speed-limit events reported by tracking data.",
                ),
                "Status": st.column_config.TextColumn(
                    "Status", help="Current or final rental status from the source data."
                ),
            },
        )


if __name__ == "__main__":
    main()
