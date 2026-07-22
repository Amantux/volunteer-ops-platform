"""API entry point for the Volunteer Operations Platform."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import app.modules.communications.service  # noqa: F401  (registers the outbox email handler)
from app.api import admin, auth, public, trainer
from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.seed import seed_bootstrap


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ready")
def ready() -> dict[str, str]:
    # Readiness: the DB is reachable.
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ready"}
