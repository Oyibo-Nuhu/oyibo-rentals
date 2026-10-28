from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import simulator
from .config import FRONTEND_DIR, PHOTO_DIR, settings
from .database import Base, SessionLocal, engine
from .routers import admin, auth, fleet, me, payments, rentals, tracking
from .seed import seed

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    task = asyncio.create_task(simulator.run_forever()) if settings.run_simulator else None
    yield
    if task:
        task.cancel()


app = FastAPI(title=f"{settings.app_name} API", version="2.0.0", lifespan=lifespan)

if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def friendly_validation(_: Request, exc: RequestValidationError):
    """Turn Pydantic errors into one readable sentence for the UI."""
    messages = []
    for err in exc.errors():
        field = " ".join(str(p) for p in err.get("loc", [])[1:]) or "input"
        messages.append(f"{field.replace('_', ' ').capitalize()}: {err.get('msg', 'invalid').replace('Value error, ', '')}")
    return JSONResponse(status_code=422, content={"detail": "; ".join(messages)})


for r in (auth.router, me.router, fleet.router, rentals.router, payments.router, tracking.router, admin.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "app": settings.app_name, "payments": "paystack" if settings.payments_live else "demo"}


@app.middleware("http")
async def revalidate_frontend(request: Request, call_next):
    """Make browsers re-check the UI files on every load so design updates show up straight away."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


PHOTO_DIR.mkdir(parents=True, exist_ok=True)
if PHOTO_DIR.resolve() != (FRONTEND_DIR / "img" / "fleet").resolve():
    # photos kept outside the code (e.g. on a persistent disk) are served at the same URL
    app.mount("/static/img/fleet", StaticFiles(directory=PHOTO_DIR), name="photos")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not found."}, status_code=404)
    return FileResponse(FRONTEND_DIR / "index.html")
