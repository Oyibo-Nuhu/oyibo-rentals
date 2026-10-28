# Rental fleet dashboard

An interactive Streamlit dashboard for exploring vehicle-rental records. It
starts with clearly labeled synthetic demo data and can also analyze a CSV
export of rental records. It is separate from the command-line rental program
in `OOP Project.py`.

## Run from VS Code

1. Open `Data Science.code-workspace` in VS Code.
2. Select a Python interpreter that has the packages in `requirements.txt`.
   If necessary, install them in the VS Code terminal:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Open **Run and Debug** and select **Rental fleet dashboard**.
4. Start debugging. The dashboard opens at `http://localhost:8501`.

You can also run it directly in the VS Code terminal:

```powershell
python -m streamlit run rental_dashboard.py
```

The VS Code launch configuration is in `.vscode/launch.json`.

## Dashboard features

- **KPI cards:** total recorded rental charges, unique rental records, average
  rental duration, currently rented records, and recorded speeding events.
- **Monthly rental charges:** sum of recorded charges by rental start month.
- **Charges by vehicle type:** total charges, rental count, and average charge.
- **Rental status mix:** share of unique rental records per status.
- **Rental distance and duration:** one point per rental, positioned by
  duration and mileage.
- **Filtered rental records:** the records underlying the current charts.
- **Sidebar filters:** rental date, vehicle type, and rental status.
- **Hover explanations:** KPI definitions are available from their labels;
  hovering a chart point or bar provides its relevant values. Captions below
  charts explain what each chart measures and how to interpret it.
- **CSV example download:** use the sidebar button to download a sample file
  with supported columns.

## CSV format

The following columns are required:

| Column | Meaning | Example |
| --- | --- | --- |
| `rental_date` | Date the rental began | `2026-10-01` |
| `vehicle_type` | Vehicle category | `Car` |
| `rental_days` | Rental duration, greater than zero | `3` |
| `final_cost` | Recorded total rental charge | `80000` |

Optional columns:

| Column | Meaning | If omitted |
| --- | --- | --- |
| `rental_id` | Unique rental identifier | Generated row IDs |
| `vehicle_id` | Identifier for the rented vehicle | `Not provided` |
| `mileage_km` | Distance driven in kilometers | `0` |
| `speeding_events` | Number of recorded speed-limit events | `0` |
| `status` | Rental status | `Returned` |

Common aliases such as `Date`, `Type`, `Days`, `Cost`, `Mileage`, and
`Rental ID` are normalized automatically. Dates must be parseable, numeric
fields must contain valid finite values, and rental days must be positive.

## Metric definitions and interpretation

- **Total rental charges** is the sum of `final_cost` for the filtered rows.
  It is recorded revenue/charges, not profit or margin.
- **Rental records** counts unique rental IDs in the filtered rows.
- **Average rental days** is the arithmetic mean of `rental_days`.
- **Currently rented** counts rows with a status of `Currently Rented`,
  `Rented`, `Active`, or `In Progress`.
- **Speeding events** sums `speeding_events`. If the source does not provide
  tracking events, its default of zero means “not supplied,” not proof that no
  speeding occurred. Include tracking data before drawing safety conclusions.
- All charts and KPIs reflect the selected date, vehicle-type, and status
  filters. A rental is grouped by its start date.
- The scatter chart can help spot unusual duration/mileage combinations; it
  does not establish a cause or indicate a verified anomaly.

## Data and tracking limitations

Demo records are generated for illustration and are not actual customer or
vehicle data. Uploaded data is processed by the local Streamlit app. This
dashboard does not connect to GPS hardware, collect live location, enforce a
vehicle speed limit, or independently verify uploaded tracking records.

## Troubleshooting

- **`No module named streamlit` or `plotly`:** select the intended Python
  interpreter in VS Code, then run `python -m pip install -r requirements.txt`
  in that interpreter.
- **Dashboard does not open:** check the VS Code terminal for startup errors.
  If port 8501 is already in use, stop the other Streamlit process or start
  this app with a different port, for example
  `python -m streamlit run rental_dashboard.py --server.port 8502`.
- **CSV upload reports missing columns:** check that the required date, type,
  duration, and charge fields are present. Download the example CSV to see
  the expected layout.
- **No results after filtering:** broaden the selected date range or select
  additional vehicle types and statuses.
