"""Production readiness guardrails — make an insecure deployment fail to START, not fail later.

`assert_production_ready` runs at startup (from the app lifespan) when environment is staging/prod.
It refuses to boot on the misconfigurations that would otherwise silently ship an insecure instance.
"""

from __future__ import annotations

from .config import Settings

# Secrets that must never reach a real environment.
_INSECURE_SECRETS = {"dev-secret-change-me", "change-me-in-prod", ""}


def _checks(s: Settings) -> list[str]:
    problems: list[str] = []
    if s.app_secret in _INSECURE_SECRETS or len(s.app_secret) < 32:
        problems.append("VOP_APP_SECRET must be a strong secret (>=32 chars), not the default")
    if s.ratelimit_backend != "redis":
        problems.append("VOP_RATELIMIT_BACKEND must be 'redis' in production (in-memory is per-node)")
    if s.botcheck_provider == "none":
        problems.append("VOP_BOTCHECK_PROVIDER must be enabled (e.g. 'turnstile') for public forms")
    if not s.public_base_url.startswith("https://"):
        problems.append("VOP_PUBLIC_BASE_URL must be https:// in production")
    if s.email_provider in ("console", "inbox"):
        problems.append("VOP_EMAIL_PROVIDER must be a real provider (e.g. 'smtp'), not a dev sink")
    return problems


def is_production(s: Settings) -> bool:
    # Normalize so VOP_ENVIRONMENT=PROD/Prod/" prod " can't silently skip the guardrails.
    return s.environment.strip().lower() in ("staging", "prod", "production")


def assert_production_ready(s: Settings) -> None:
    """Raise RuntimeError listing every insecure setting, so the instance refuses to start."""
    if not is_production(s):
        return
    problems = _checks(s)
    if problems:
        raise RuntimeError(
            "Refusing to start in a production environment with insecure configuration:\n  - "
            + "\n  - ".join(problems)
        )
