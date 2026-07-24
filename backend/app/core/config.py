"""Runtime settings, read from the environment (prefix VOP_)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VOP_", env_file=".env", extra="ignore")

    # Datastore. Postgres in compose/prod; tests override with SQLite for speed.
    database_url: str = "postgresql+psycopg://vop:vop@localhost:5432/vop"
    redis_url: str = "redis://localhost:6379/0"

    # App secret for signing tokens (magic links, verification). CHANGE IN PROD.
    app_secret: str = "dev-secret-change-me"

    # First-run bootstrap org + admin.
    bootstrap_org_name: str = "Community Volunteers"
    bootstrap_org_slug: str = "community"
    bootstrap_admin_email: str = "admin@example.org"

    # Email provider: "console" (dev, logs), "inbox" (dev, DB table), or "smtp" (real:
    # Postmark/SES/any SMTP). Selected by adapter factory.
    email_provider: str = "inbox"
    email_from: str = "Community Volunteers <no-reply@example.org>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    # Payments (Stripe) — scaffolded for the donations phase; unused in the training slice.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Public base URL for links in emails.
    public_base_url: str = "http://localhost:3000"

    # Token lifetimes (minutes).
    verification_token_ttl_min: int = 60 * 24
    activation_token_ttl_min: int = 60 * 24 * 7

    # Unverified "registered" holds expire (freeing the seat) after this long.
    unconfirmed_hold_ttl_min: int = 60 * 24

    # LLM drafting assist (optional). "dev" = deterministic local stub (default, no key needed);
    # "anthropic" = real API when llm_api_key is set. AI is assist-only; nothing auto-publishes.
    llm_provider: str = "dev"
    llm_api_key: str = ""
    llm_model: str = ""

    # Social publishing. "manual" (default: mark posted + export copy, no external effect) or
    # "webhook" (POST to social_webhook_url, e.g. Zapier). Real platform adapters are deferred.
    social_publisher: str = "manual"
    social_webhook_url: str = ""

    # Rate limiting: "memory" (single node/dev/tests) | "redis" (multi-node/prod).
    ratelimit_backend: str = "memory"
    # Public-form bot control: "none" (dev) | "turnstile" (Cloudflare Turnstile).
    botcheck_provider: str = "none"
    turnstile_secret: str = ""


settings = Settings()
