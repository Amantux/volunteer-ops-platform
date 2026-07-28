"""Chat assistant endpoints: a streaming (SSE) chat for signed-in users, and admin-only settings
to configure the per-org provider (Ollama/Anthropic). The assistant is read-only + governed
(see app.modules.agents.assistant); nothing here can send, publish, or move money."""

from __future__ import annotations

import json
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.authz import Principal
from app.modules.agents import assistant

from .deps import current_principal, get_db, require_permission

router = APIRouter(prefix="/api", tags=["assistant"])


class ChatMessage(BaseModel):
    role: str
    content: str = Field(max_length=8000)


class ChatIn(BaseModel):
    # Bound the body: server also keeps only the last 20 messages, but cap here so a giant payload
    # can't be parsed/copied first.
    messages: list[ChatMessage] = Field(max_length=100)


@router.get("/agent/config")
def agent_config(db: Session = Depends(get_db),
                 principal: Principal = Depends(current_principal)):
    cfg = assistant.resolve_config(db, principal.org_id)
    return {"enabled": cfg.enabled, "provider": cfg.provider, "model": cfg.model}


@router.post("/agent/chat")
def agent_chat(payload: ChatIn, request: Request, db: Session = Depends(get_db),
               principal: Principal = Depends(current_principal)):
    if not ratelimit.allow(f"assistant:{principal.user_id}", limit=30, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many messages — slow down a moment.")
    messages = [m.model_dump() for m in payload.messages]

    def _events():
        for ev in assistant.stream_chat(db, principal, messages):
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- Admin configuration --------------------------------------------------------------- #

_PROVIDERS = ("off", "ollama", "openai", "anthropic")


class AgentSettingsIn(BaseModel):
    provider: str | None = None       # off | ollama | anthropic
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None        # blank on save = keep existing
    system_prompt: str | None = None
    timeout: int | None = None
    max_steps: int | None = None


@router.get("/admin/agent-settings")
def get_agent_settings(db: Session = Depends(get_db),
                       principal: Principal = Depends(require_permission("assistant.configure"))):
    return assistant.public_config(assistant.resolve_config(db, principal.org_id))


@router.put("/admin/agent-settings")
def put_agent_settings(payload: AgentSettingsIn, db: Session = Depends(get_db),
                       principal: Principal = Depends(require_permission("assistant.configure"))):
    patch = payload.model_dump(exclude_none=True)
    if "provider" in patch and patch["provider"] not in _PROVIDERS:
        raise HTTPException(status_code=400, detail="invalid provider")
    if "base_url" in patch and not assistant.is_safe_url(patch["base_url"]):
        raise HTTPException(status_code=400, detail="base_url must be http(s) to a permitted host")
    assistant.set_org_config(db, principal.org_id, patch)
    db.commit()
    return assistant.public_config(assistant.resolve_config(db, principal.org_id))


@router.post("/admin/agent-settings/models")
def list_models(db: Session = Depends(get_db),
                principal: Principal = Depends(require_permission("assistant.configure"))):
    """Probe the configured provider for its installed models (populates the admin dropdown).
    Ollama → /api/tags; OpenAI-style → /v1/models (both with the API key when set)."""
    cfg = assistant.resolve_config(db, principal.org_id)
    if cfg.provider not in ("ollama", "openai") or not cfg.base_url:
        return {"models": []}
    if not assistant.is_safe_url(cfg.base_url):
        raise HTTPException(status_code=400, detail="base_url not permitted")
    path = "/api/tags" if cfg.provider == "ollama" else "/models"
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    try:
        req = urllib.request.Request(cfg.base_url.rstrip("/") + path, headers=headers)
        with assistant._guarded_open(req, timeout=cfg.timeout) as r:
            data = json.loads(r.read().decode())
    except Exception as exc:  # noqa: BLE001 - generic error; don't leak internal reachability
        raise HTTPException(status_code=502, detail="Could not reach the model provider.") from exc
    if cfg.provider == "ollama":
        return {"models": [m.get("name") for m in data.get("models", [])]}
    return {"models": [m.get("id") for m in data.get("data", [])]}
