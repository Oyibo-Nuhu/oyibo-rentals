"""Settings read from environment variables (see .env.example)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"


def _load_dotenv(path: Path) -> None:
    """Minimal .env support for local runs. Real environment variables always win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if "PYTEST_CURRENT_TEST" not in os.environ and not os.getenv("OYIBO_SKIP_DOTENV"):
    _load_dotenv(BASE_DIR / ".env")

# Vehicle photos live under the frontend so they are served at /static/img/fleet/.
PHOTO_DIR = Path(os.getenv("PHOTO_DIR", FRONTEND_DIR / "img" / "fleet"))
# Driver's licence photos are private: kept outside the website folder and shown to admins only.
LICENCE_DIR = Path(os.getenv("LICENCE_DIR", BASE_DIR / "uploads" / "licences"))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'oyibo_rentals.db'}")
    # Render/Heroku style URLs need the SQLAlchemy driver name.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Settings:
    app_name = os.getenv("APP_NAME", "Oyibo Rentals")
    database_url = _database_url()
    jwt_secret = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
    jwt_hours = int(os.getenv("JWT_HOURS", "12"))
    admin_email = os.getenv("ADMIN_EMAIL", "admin@oyibo.ng").lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
    paystack_secret = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    public_url = os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/")
    seed_demo_data = _bool("SEED_DEMO_DATA", True)
    run_simulator = _bool("RUN_TRACKING_SIMULATOR", True)
    # Map tiles. OpenStreetMap's free server is fine for a demo; for real traffic use a provider
    # such as MapTiler or Stadia and paste its URL (with your key) here.
    map_tile_url = os.getenv("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    map_attribution = os.getenv("MAP_ATTRIBUTION", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors')
    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

    @property
    def payments_live(self) -> bool:
        return bool(self.paystack_secret)


settings = Settings()
