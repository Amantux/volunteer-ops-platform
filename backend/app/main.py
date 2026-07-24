"""API entry point for the Volunteer Operations Platform."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, comms, content, ops, public, scheduling, social, trainer
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
    # Fail fast on incomplete provider config rather than silently dropping mail.
    if settings.email_provider == "smtp" and not settings.smtp_host:
        raise RuntimeError("VOP_EMAIL_PROVIDER=smtp requires VOP_SMTP_HOST to be set.")
    if settings.llm_provider == "anthropic" and not settings.llm_api_key:
        raise RuntimeError("VOP_LLM_PROVIDER=anthropic requires VOP_LLM_API_KEY to be set.")
    if settings.social_publisher == "webhook" and not settings.social_webhook_url:
        raise RuntimeError("VOP_SOCIAL_PUBLISHER=webhook requires VOP_SOCIAL_WEBHOOK_URL.")
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
app.include_router(content.admin_router)
app.include_router(content.public_router)
app.include_router(social.router)
app.include_router(ops.router)

# Import the social service so its "social.publish" outbox handler registers at startup.
from app.modules.social import service as _social_service  # noqa: E402,F401


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
