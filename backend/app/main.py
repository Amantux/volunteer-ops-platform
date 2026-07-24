"""API entry point for the Volunteer Operations Platform."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import admin, auth, comms, public, scheduling, trainer
from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.modules.communications import service as _comms  # noqa: F401  (registers outbox handler)
from app.seed import seed_bootstrap

_INSECURE_SECRETS = {"dev-secret-change-me", "change-me-in-prod"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast if a real email provider is configured with an insecure app secret:
    # session tokens and verification-token hashes derive from it.
    if settings.app_secret in _INSECURE_SECRETS:
        if settings.email_provider == "smtp":
            raise RuntimeError(
                "VOP_APP_SECRET is still the default — refusing to start with a real email "
                "provider. Set a strong secret."
            )
        print("WARNING: VOP_APP_SECRET is the default dev value. Set VOP_APP_SECRET before "
              "deploying.")
    init_db()
    with SessionLocal() as db:
        seed_bootstrap(db)
    yield


app = FastAPI(title="Volunteer Operations Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_base_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(public.router)
app.include_router(auth.router)
app.include_router(trainer.router)
app.include_router(admin.router)
app.include_router(scheduling.router)
app.include_router(comms.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ready")
def ready() -> dict[str, str]:
    # Readiness: the DB is reachable.
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ready"}
