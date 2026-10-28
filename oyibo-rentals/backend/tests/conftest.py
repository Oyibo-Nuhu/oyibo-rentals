"""Every test run uses a throwaway SQLite database with no demo data and no simulator."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp())
os.environ["OYIBO_SKIP_DOTENV"] = "1"
os.environ.update(DATABASE_URL=f"sqlite:///{_tmp / 'test.db'}", PHOTO_DIR=str(_tmp / "photos"),
                  LICENCE_DIR=str(_tmp / "licences"), SEED_DEMO_DATA="false", RUN_TRACKING_SIMULATOR="false",
                  JWT_SECRET="test-secret-that-is-long-enough-for-hs256-ok", ADMIN_EMAIL="admin@test.ng", ADMIN_PASSWORD="AdminPass123!",
                  PAYSTACK_SECRET_KEY="")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin(client):
    r = client.post("/api/auth/login", json={"email": "admin@test.ng", "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    return auth(r.json()["token"])


def licence_photo() -> bytes:
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (900, 560), (230, 240, 230)).save(buf, "JPEG")
    return buf.getvalue()


def submit_licence(client, headers, kind="full", number="LAG-12345-AA01", expires="2030-01-31"):
    return client.post("/api/me/licence", headers=headers, data={"kind": kind, "number": number, "expires_on": expires,
                                                                 "state": "Lagos"},
                       files={"file": ("licence.jpg", licence_photo(), "image/jpeg")})


@pytest.fixture(scope="session")
def customer(client):
    r = client.post("/api/auth/register", json={"name": "Nuhu Oyibo", "email": "nuhu@test.ng",
                                                "phone": "08039378598", "password": "Lagos#Drive2026"})
    assert r.status_code == 200, r.text
    headers = auth(r.json()["token"])
    assert submit_licence(client, headers).status_code == 200   # self-drive needs a licence
    return headers
