# Oyibo Rentals

Rent anything that moves in Lagos: luxury cars, SUVs, buses, pickups, trucks, bikes and kekes.
A full-stack web app grown from my Python OOP vehicle rental project and my Streamlit rental dashboard.

**By Oyibo Nuhu Ojochogwu · Foundation in Data Science**

| For customers | For admins (Control room) |
| --- | --- |
| Sign up / log in with a wink-and-zoom launch animation | Alerts feed (speeding, SOS, low fuel) |
| Fleet of 43 vehicles in 7 classes, with real photos | **Live GPS**: every active vehicle on the map with live speed, trails, a follow panel with speedometer, red alerts over 100 km/h |
| Oyibo points, referral codes, EV and Spiro bike rides | Interactive analytics: filters, cross-filtering, revenue race, Lagos pickup map, daily calendar, pricing what-if |
| Four ways to pay: **route** (A→B, timed), **half day**, **full day**, **cross country** | Demand forecast with backtest, customer segments (k-means), driver risk scores |
| Rush-hour pricing, driver add-on, green-ride discount, "pay small small" | Insurance loss ratios, fleet utilization, CSV export and CSV analysis |
| Damage insurance (Basic / Standard / Premium) and in-app damage claims | Fleet management: add vehicles to any class with a photo, set each vehicle Available / Unavailable / In workshop, change prices, replace photos |
| Live trip page: countdown, speed (100 km/h cap), map, SOS | Claims review, customer list |
| Card, bank transfer and USSD checkout (Paystack, or demo mode) | Original CSV dashboard still works inside Analytics |
| **Profile page**: trips, km, spend, points, edit details, change password, referral code | **Licence queue**: view each uploaded licence photo, verify or reject with a reason (the customer is notified) |
| **Self-drive needs a full driver's licence** (photo + number + expiry). Learner's permits and expired licences are refused; or book with an Oyibo driver | **Send speed warning** to the driver of any self-drive trip from the Live GPS panel, with their strike count |
| **Speeding rule**: 3 warnings per trip by notification, then ₦5,000 per incident from the deposit (one incident = one continuous stretch over 100 km/h; trips with our driver never count) | Pending-licence badge in the sidebar |
| Notification bell with live toasts, collapsible sidebar, smooth page transitions, synthesised "vroom" engine sound (mute button in the sidebar) | |

## How the original projects became this app

| Original | Where it lives now |
| --- | --- |
| `legacy/OOP Project.py` — `Vehicle`, `Car`, `Motorcycle`, `Truck`, `Rental`, `RentalSystem` | `backend/app/engine.py` keeps the same classes and rules (encapsulated rate, polymorphic cost, 5/10/15% discounts, free 100 km, 20% late fee, deposit, empty-location and speed checks) and adds `LuxuryCar`, `ExecutiveCar`, `CommercialVehicle` and `Tricycle` (keke), rental modes, insurance and VAT. |
| `legacy/rental_dashboard.py` — CSV cleaning, KPIs, four charts | `backend/app/analytics.py` keeps `standardize_rental_data`, `build_monthly_summary` and the KPI definitions, runs them on live data, and adds forecasting, segmentation, risk scoring and the interactive dashboard data. You can still upload a CSV in the Control room. |

## Project layout

```
oyibo-rentals/
├── backend/
│   ├── app/
│   │   ├── engine.py        # rental rules (from the OOP project); no web code, unit-tested
│   │   ├── analytics.py     # data science (from the dashboard)
│   │   ├── main.py          # FastAPI app; serves the API and the frontend
│   │   ├── routers/         # auth, fleet, rentals, payments, tracking, admin
│   │   ├── models.py        # database tables (SQLAlchemy)
│   │   ├── seed.py          # fleet list + clearly-flagged demo history
│   │   ├── simulator.py     # simulated GPS for active rentals
│   │   └── payments.py      # Paystack (or demo checkout)
│   ├── scripts/fetch_vehicle_photos.py
│   ├── tests/               # pytest: engine rules + full API flows
│   └── requirements.txt
├── frontend/                # plain HTML/CSS/JS, no build step
│   ├── index.html, styles.css
│   ├── js/                  # app, booking, trips, admin, analytics, mascot/launch
│   └── img/fleet/           # vehicle photos + credits.json
├── legacy/                  # the original OOP project and Streamlit dashboard
├── Dockerfile               # one container for API + site
├── render.yaml              # one-click deploy on Render (app + PostgreSQL)
└── .env.example             # every setting, explained
```

## 1. Run it on your computer (VS Code)

You need Python 3.11 or newer.

```powershell
cd oyibo-rentals
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements-dev.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
cd backend
python -m uvicorn app.main:app --reload
```

Open http://localhost:8000. Or in VS Code: **Run and Debug → "Oyibo Rentals (web app)"**.

The original Streamlit dashboard still runs too: `pip install -r legacy/requirements.txt`, then
**Run and Debug → "Original rental dashboard (Streamlit)"**.

The first start creates a local SQLite database (`oyibo_rentals.db`) with the fleet and demo history.
Delete that file any time to start fresh.

**Log in to try it**

- Customer demo: `demo@oyibo.ng` / `Demo1234!` (or create your own account)
- Admin: the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from your `.env` (defaults: `admin@oyibo.ng` / `ChangeMe123!`)

**Run the tests**

```powershell
cd backend
python -m pytest -q
```

## 2. Put it on GitHub

1. Create an empty repository on GitHub (no README), e.g. `oyibo-rentals`.
2. In the project folder:

```powershell
git init                       # skip if the folder already has a .git folder
git add .
git commit -m "Oyibo Rentals: full-stack rental app"
git branch -M main
git remote add origin https://github.com/<your-username>/oyibo-rentals.git
git push -u origin main
```

`.gitignore` keeps your `.env` (secrets) and the local database out of Git.
Every push runs the tests on GitHub Actions (`.github/workflows/tests.yml`); look for the green tick.

## 3. Deploy on Render (app + database)

1. Sign in at https://render.com with your GitHub account.
2. **New + → Blueprint**, choose your `oyibo-rentals` repository. Render reads `render.yaml` and creates:
   - **oyibo-rentals**: the web app, built from the `Dockerfile`
   - **oyibo-db**: a PostgreSQL database, connected automatically
3. Render asks for the settings marked `sync: false`:
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD`: your admin login (use a strong password)
   - `PAYSTACK_SECRET_KEY`: leave empty for demo checkout, or paste a `sk_test_…` key
   - `PUBLIC_URL`: your Render address, e.g. `https://oyibo-rentals.onrender.com` (you can fill it in after the first deploy)
4. Click **Apply**. The first build takes a few minutes. When it shows **Live**, open the URL.

Free Render plans have limits (for example, free web services sleep when idle and wake on the next visit,
and free databases are time-limited). Check Render's pricing page and upgrade when you have real customers.

**Other hosts.** Any host that runs a Dockerfile works (Railway, Fly.io, a VPS with Docker).
Set the environment variables from `.env.example`, give it a PostgreSQL `DATABASE_URL`, and expose port 8000
(or set `PORT`).

## 4. Before real customers use it

- [ ] **Change the admin password** and keep `JWT_SECRET` long and secret (Render generates one).
- [ ] **Turn off demo data**: set `SEED_DEMO_DATA=false` on a **fresh** database. Demo customers and rentals are flagged
      (`users.is_demo`) if you need to remove them from an existing database.
- [ ] **Payments**: create a Paystack account, test with `sk_test_…`, then switch to `sk_live_…`.
      Set the webhook URL in Paystack to `https://<your-site>/api/payments/webhook`.
- [ ] **Tracking**: set `RUN_TRACKING_SIMULATOR=false` once real GPS trackers or a driver app send pings to
      `POST /api/tracking/{code}/ping` (location, lat, lng, speed_kmh). Empty locations are rejected and speeds over
      100 km/h raise an alert, exactly like the original project.
- [ ] **Maps**: OpenStreetMap's free tile server is for light use. For real traffic, get a key from a tile provider
      (MapTiler, Stadia Maps…) and set `MAP_TILE_URL` and `MAP_ATTRIBUTION`.
- [ ] **Photos you upload** in the admin Fleet tab are saved on the server's disk. On hosts with temporary disks (like
      Render's free plan) they disappear on redeploy: attach a persistent disk and set `PHOTO_DIR` to it, or commit
      your photos to `frontend/img/fleet/` instead.
- [ ] **Licence photos** are kept in `LICENCE_DIR` (default `uploads/licences`, git-ignored) and only admins can open them.
      Put them on a persistent disk too (`LICENCE_DIR=/var/data/licences`). They are for checking only: staff should
      still see the physical licence at pickup.

## Vehicle photos

Photos come from Wikipedia / Wikimedia Commons under free licences (Creative Commons or public domain).
The author and licence show on every photo and are stored in `frontend/img/fleet/credits.json`.
Keep those credits if you reuse the photos.

- Add a vehicle to `FLEET` and `PHOTO_ARTICLES` in `backend/app/seed.py`, then fetch its photo:
  `python scripts/fetch_vehicle_photos.py <VEHICLE-ID>` (from `backend/`). Wikimedia limits request rates, so the
  script waits and retries; re-run it to fill any gaps.
- Or use your own photo: upload it in **Control room → Fleet**, or drop `<VEHICLE-ID>.jpg` into `frontend/img/fleet/`
  and add a credits entry with `"author": "Oyibo Rentals"`.
- Vehicles without a photo show an illustration.

## API

FastAPI documents every endpoint at `/docs` on your running app (e.g. http://localhost:8000/docs).

## The mascot

Zuma (named after Zuma Rock) is the app's own original character: a glossy EV coupe whose headlight is an eye.
It winks and zooms off after every login, shuts its eye while you type a password, and celebrates after payment.
