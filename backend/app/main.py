"""API entry point for the Volunteer Operations Platform."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import (
    admin,
    agent,
    auth,
    comms,
    content,
    dashboard,
    donations,
    forms,
    ops,
    people,
    public,
    scheduling,
    social,
    trainer,
)
from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.core.production import assert_production_ready, is_production
from app.modules.communications import service as _comms  # noqa: F401  (registers outbox handler)
from app.seed import seed_bootstrap

_INSECURE_SECRETS = {"dev-secret-change-me", "change-me-in-prod"}


def _init_sentry() -> None:
    """Wire error tracking when a DSN is configured. No-op (and never fatal) otherwise."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment,
                        traces_sample_rate=0.0, send_default_pii=False)
    except Exception as exc:  # noqa: BLE001 - observability must never take the app down
        print(f"WARNING: Sentry init failed ({exc}); continuing without error tracking.")


_init_sentry()


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
    # Refuse to start in staging/prod with an insecure configuration.
    assert_production_ready(settings)
    # In production, migrations (`alembic upgrade head`, run as a deploy step) are the source of
    # truth for the schema — never create_all. Demo content is only seeded outside production.
    if not is_production(settings):
        init_db()
    with SessionLocal() as db:
        seed_bootstrap(db, include_demo=not is_production(settings))
    yield


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers on every API response (HSTS only when in production/https)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if is_production(settings):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response


app = FastAPI(title="Volunteer Operations Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_base_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Accept"],
)

app.include_router(public.router)
app.include_router(auth.router)
app.include_router(trainer.router)
app.include_router(admin.router)
app.include_router(scheduling.router)
app.include_router(people.router)
app.include_router(donations.public_router)
app.include_router(donations.admin_router)
app.include_router(dashboard.router)
app.include_router(agent.router)
app.include_router(comms.router)
app.include_router(content.admin_router)
app.include_router(content.public_router)
app.include_router(social.router)
app.include_router(forms.admin)
app.include_router(forms.public)
app.include_router(ops.router)

# Import the social + workflows services so their outbox handlers register at startup.
from app.modules.social import service as _social_service  # noqa: E402,F401
from app.modules.workflows import service as _workflows_service  # noqa: E402,F401


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
